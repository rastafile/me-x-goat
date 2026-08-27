"""HTTP endpoints and turn orchestration. No chess logic lives here -- it
calls game.py, engine.py, and persona.py and shapes their output as JSON.

Holds exactly one game in memory, in app.state: this is a local, single-user
app, not a multi-tenant service. No sessions, no auth, no game IDs.
"""

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import chess
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.coach import narrate_goat_move
from src.engine import Analysis, Candidate, Engine, EngineUnavailable
from src.game import Game, IllegalMove
from src.narration import DEFAULT_LANGUAGE, LANGUAGES
from src.persona import choose
from src.tutor import Assessment, assess

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Same shape and interpolation as persona._margin_cp's table; this is an
# orchestration decision (how long to let the engine think), which belongs
# here, not in engine.py or persona.py.
_ANALYSIS_TIME_TABLE = [
    (800, 50),
    (1200, 100),
    (1600, 200),
    (2000, 400),
    (2400, 800),
]

_MISTAKE_TIERS = ("inaccuracy", "mistake", "blunder")


def _fresh_mistake_counts() -> dict[str, dict[str, int]]:
    return {
        "white": {tier: 0 for tier in _MISTAKE_TIERS},
        "black": {tier: 0 for tier in _MISTAKE_TIERS},
    }


class NewGameRequest(BaseModel):
    color: Literal["white", "black", "random"] = "random"
    strength: int = Field(default=1400, ge=800, le=2800)
    style: Literal["carlsen", "raw"] = "carlsen"
    # Not a Literal: an unrecognized value should fall back to
    # DEFAULT_LANGUAGE, not reject the request -- same rule web/i18n.js
    # already applies client-side, kept in _new_game_language below.
    language: str = DEFAULT_LANGUAGE


class MoveRequest(BaseModel):
    uci: str


class GoatMove(BaseModel):
    uci: str
    san: str
    tags: list[str]
    commentary: str


class AssessmentResponse(BaseModel):
    classification: str
    loss_cp: int
    best_move: str | None
    continuation: list[str]
    offer_take_back: bool


class SummaryResponse(BaseModel):
    mistake_counts: dict[str, dict[str, int]]
    decided_at_ply: int
    decided_by: Literal["white", "black"]
    loss_cp: int


class GameStateResponse(BaseModel):
    fen: str
    user_color: Literal["white", "black"]
    legal_moves: list[str]
    goat_move: GoatMove | None
    tutor: AssessmentResponse | None
    mistake_counts: dict[str, dict[str, int]]
    summary: SummaryResponse | None
    evaluation: int | None
    is_over: bool
    outcome: str | None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        engine = Engine(path=os.environ.get("STOCKFISH_PATH", "stockfish"))
    except EngineUnavailable:
        print("Stockfish not found. Install it and try again:", file=sys.stderr)
        print("  macOS:  brew install stockfish", file=sys.stderr)
        print("  Debian: sudo apt install stockfish", file=sys.stderr)
        raise

    app.state.engine = engine
    app.state.game = None
    app.state.style = "carlsen"
    app.state.strength = 1400
    app.state.language = DEFAULT_LANGUAGE
    app.state.mistake_counts = _fresh_mistake_counts()
    # One entry per ply ever pushed via /move (both the user's and the
    # GOAT's), kept in lockstep with game.ply_count -- (color, Assessment)
    # when the ply was actually assessed, None otherwise (the opening move
    # played from /new-game, or a move with no "after" analysis because it
    # ended the game). /take-back pops this alongside game.pop() to undo
    # whatever mistake count that ply had added.
    app.state.assessment_history = []
    yield
    engine.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_WEB_DIR / "index.html")


@app.post("/new-game", response_model=GameStateResponse)
def new_game(body: NewGameRequest) -> GameStateResponse:
    game = Game(user_color=body.color)
    app.state.game = game
    app.state.style = body.style
    app.state.strength = body.strength
    app.state.language = body.language if body.language in LANGUAGES else DEFAULT_LANGUAGE
    app.state.mistake_counts = _fresh_mistake_counts()
    app.state.assessment_history = []

    goat_move, analysis = None, None
    if not game.waiting_for_user:
        goat_move, analysis = _play_goat_move(
            game, app.state.engine, body.style, body.strength, app.state.language
        )
        app.state.assessment_history.append(None)  # opening move, not assessed

    return _state_response(
        game,
        goat_move,
        analysis,
        tutor=None,
        mistake_counts=app.state.mistake_counts,
        assessment_history=app.state.assessment_history,
    )


@app.post("/move", response_model=GameStateResponse)
def make_move(body: MoveRequest) -> GameStateResponse:
    game: Game | None = app.state.game
    if game is None:
        raise HTTPException(status_code=400, detail="no game in progress; call /new-game first")

    # Capture the pre-move FEN and validate the move (cheap) before spending
    # an analyse() call (not cheap) on it -- an illegal move should never
    # reach the engine at all.
    fen_before_move = game.fen
    try:
        game.push(body.uci)
    except IllegalMove as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    before = app.state.engine.analyse(fen_before_move, movetime_ms=_movetime_ms(app.state.strength))
    user_color = game.user_color

    goat_move, analysis = None, None
    if not game.is_over():
        goat_move, analysis = _play_goat_move(
            game, app.state.engine, app.state.style, app.state.strength, app.state.language
        )

    # analysis is the opponent's analysis of the position the user's move
    # left behind -- exactly the "after" half tutor.assess needs, already
    # paid for by _play_goat_move above. None only when the user's own move
    # ended the game, and there's nothing left to analyse.
    tutor_assessment = None
    if analysis is not None:
        tutor_assessment = assess(before, body.uci, analysis, user_color)
    _track_assessment(app.state.assessment_history, app.state.mistake_counts, user_color, tutor_assessment)

    # The GOAT's own move gets the same treatment, for the "both sides"
    # mistake count design.md asks for -- tutor.assess doesn't care whose
    # move it classifies (ADR 4), so this is a policy choice, not a design
    # change. Costs one further analyse() call, on the position after the
    # GOAT's own reply.
    if goat_move is not None:
        goat_color = "black" if user_color == "white" else "white"
        goat_assessment = None
        if not game.is_over():
            after_goat = app.state.engine.analyse(game.fen, movetime_ms=_movetime_ms(app.state.strength))
            goat_assessment = assess(analysis, goat_move.uci, after_goat, goat_color)
        _track_assessment(app.state.assessment_history, app.state.mistake_counts, goat_color, goat_assessment)

    return _state_response(
        game,
        goat_move,
        analysis,
        tutor_assessment,
        mistake_counts=app.state.mistake_counts,
        assessment_history=app.state.assessment_history,
    )


@app.post("/take-back", response_model=GameStateResponse)
def take_back() -> GameStateResponse:
    game: Game | None = app.state.game
    if game is None:
        raise HTTPException(status_code=400, detail="no game in progress; call /new-game first")

    # Normally two plies -- the user's move and the GOAT's reply -- except
    # right after a Black game's opening, where only the GOAT's single
    # opening move is on the stack yet (docs/week-1.md flagged this
    # asymmetry without resolving it).
    plies_to_pop = min(game.ply_count, 2)
    if plies_to_pop == 0:
        raise HTTPException(status_code=400, detail="nothing to take back")

    for _ in range(plies_to_pop):
        game.pop()
        undone = app.state.assessment_history.pop()
        if undone is not None:
            color, assessment = undone
            _adjust_mistake_count(app.state.mistake_counts, color, assessment.classification, -1)

    return _state_response(
        game,
        goat_move=None,
        analysis=None,
        tutor=None,
        mistake_counts=app.state.mistake_counts,
        assessment_history=app.state.assessment_history,
    )


@app.get("/pgn")
def get_pgn() -> PlainTextResponse:
    game: Game | None = app.state.game
    if game is None:
        raise HTTPException(status_code=400, detail="no game in progress; call /new-game first")
    return PlainTextResponse(game.pgn())


def _play_goat_move(
    game: Game, engine: Engine, style: str, strength: int, language: str
) -> tuple[GoatMove, Analysis]:
    analysis = engine.analyse(game.fen, movetime_ms=_movetime_ms(strength))
    board_before = chess.Board(game.fen)
    result = choose(game.fen, analysis.candidates, style=style, strength=strength)
    game.push(result.move)
    san = board_before.san(chess.Move.from_uci(result.move))
    # narrate_goat_move expects `game` to already reflect the position after
    # `result.move` -- true here, since it's called right after the push.
    commentary = narrate_goat_move(analysis, result, game, language)
    return GoatMove(uci=result.move, san=san, tags=result.tags, commentary=commentary), analysis


def _track_assessment(
    assessment_history: list[tuple[str, Assessment] | None],
    mistake_counts: dict[str, dict[str, int]],
    color: str,
    assessment: Assessment | None,
) -> None:
    """Appends one entry to assessment_history, keeping it in lockstep with
    game.ply_count, and increments mistake_counts if the assessment
    qualifies. `assessment=None` records a ply that was never assessed (the
    move ended the game before an "after" analysis was possible)."""
    if assessment is None:
        assessment_history.append(None)
        return
    assessment_history.append((color, assessment))
    _adjust_mistake_count(mistake_counts, color, assessment.classification, 1)


def _adjust_mistake_count(
    mistake_counts: dict[str, dict[str, int]], color: str, classification: str, delta: int
) -> None:
    if classification in _MISTAKE_TIERS:
        mistake_counts[color][classification] += delta


def _summary(
    game: Game,
    assessment_history: list[tuple[str, Assessment] | None],
    mistake_counts: dict[str, dict[str, int]],
) -> SummaryResponse | None:
    """Recomputed from assessment_history on demand rather than tracked
    incrementally: take-back already pops that history in lockstep with
    game.pop(), so recomputing "the worst ply so far" from whatever is
    actually left there is correct for free, including across repeated
    take-backs -- no separate undo logic needed for this."""
    if not game.is_over():
        return None

    worst: tuple[int, str, Assessment] | None = None
    for ply, entry in enumerate(assessment_history, start=1):
        if entry is None:
            continue
        color, assessment = entry
        if worst is None or assessment.loss_cp > worst[2].loss_cp:
            worst = (ply, color, assessment)

    if worst is None:
        # Every ply this game was untracked (e.g. it ended before any move
        # ever got an "after" analysis) -- nothing to name as the turning
        # point.
        return None

    ply, color, assessment = worst
    return SummaryResponse(
        mistake_counts=mistake_counts,
        decided_at_ply=ply,
        decided_by=color,
        loss_cp=assessment.loss_cp,
    )


def _state_response(
    game: Game,
    goat_move: GoatMove | None,
    analysis: Analysis | None,
    tutor: Assessment | None,
    mistake_counts: dict[str, dict[str, int]],
    assessment_history: list[tuple[str, Assessment] | None],
) -> GameStateResponse:
    top_candidate: Candidate | None = None
    if analysis is not None and analysis.candidates:
        top_candidate = analysis.candidates[0]

    tutor_response = None
    if tutor is not None:
        tutor_response = AssessmentResponse(
            classification=tutor.classification,
            loss_cp=tutor.loss_cp,
            best_move=tutor.best_move,
            continuation=tutor.continuation,
            offer_take_back=tutor.offer_take_back,
        )

    return GameStateResponse(
        fen=game.fen,
        user_color=game.user_color,
        legal_moves=game.legal_moves(),
        goat_move=goat_move,
        tutor=tutor_response,
        mistake_counts=mistake_counts,
        summary=_summary(game, assessment_history, mistake_counts),
        evaluation=_evaluation_for_user(top_candidate, game.user_color),
        is_over=game.is_over(),
        outcome=game.outcome(),
    )


def _evaluation_for_user(candidate: Candidate | None, user_color: str) -> int | None:
    if candidate is None or candidate.score_cp is None:
        return None
    return candidate.score_cp if user_color == "white" else -candidate.score_cp


def _movetime_ms(strength: int) -> int:
    table = _ANALYSIS_TIME_TABLE
    if strength <= table[0][0]:
        return table[0][1]
    if strength >= table[-1][0]:
        return table[-1][1]
    for (lo_strength, lo_time), (hi_strength, hi_time) in zip(table, table[1:]):
        if lo_strength <= strength <= hi_strength:
            t = (strength - lo_strength) / (hi_strength - lo_strength)
            return round(lo_time + t * (hi_time - lo_time))
    raise AssertionError("unreachable: strength is clamped to the table's range above")
