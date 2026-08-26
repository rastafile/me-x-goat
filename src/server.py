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

from src.engine import Analysis, Candidate, Engine, EngineUnavailable
from src.game import Game, IllegalMove
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


class NewGameRequest(BaseModel):
    color: Literal["white", "black", "random"] = "random"
    strength: int = Field(default=1400, ge=800, le=2800)
    style: Literal["carlsen", "raw"] = "carlsen"


class MoveRequest(BaseModel):
    uci: str


class GoatMove(BaseModel):
    uci: str
    san: str
    tags: list[str]


class AssessmentResponse(BaseModel):
    classification: str
    loss_cp: int
    best_move: str | None
    continuation: list[str]
    offer_take_back: bool


class GameStateResponse(BaseModel):
    fen: str
    user_color: Literal["white", "black"]
    legal_moves: list[str]
    goat_move: GoatMove | None
    tutor: AssessmentResponse | None
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

    goat_move, analysis = None, None
    if not game.waiting_for_user:
        goat_move, analysis = _play_goat_move(game, app.state.engine, body.style, body.strength)

    return _state_response(game, goat_move, analysis, tutor=None)


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

    goat_move, analysis = None, None
    if not game.is_over():
        goat_move, analysis = _play_goat_move(game, app.state.engine, app.state.style, app.state.strength)

    # analysis is the opponent's analysis of the position the user's move
    # left behind -- exactly the "after" half tutor.assess needs, already
    # paid for by _play_goat_move above. None only when the user's own move
    # ended the game, and there's nothing left to analyse.
    tutor_assessment = None
    if analysis is not None:
        tutor_assessment = assess(before, body.uci, analysis, game.user_color)

    return _state_response(game, goat_move, analysis, tutor_assessment)


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

    return _state_response(game, goat_move=None, analysis=None, tutor=None)


@app.get("/pgn")
def get_pgn() -> PlainTextResponse:
    game: Game | None = app.state.game
    if game is None:
        raise HTTPException(status_code=400, detail="no game in progress; call /new-game first")
    return PlainTextResponse(game.pgn())


def _play_goat_move(
    game: Game, engine: Engine, style: str, strength: int
) -> tuple[GoatMove, Analysis]:
    analysis = engine.analyse(game.fen, movetime_ms=_movetime_ms(strength))
    board_before = chess.Board(game.fen)
    result = choose(game.fen, analysis.candidates, style=style, strength=strength)
    game.push(result.move)
    san = board_before.san(chess.Move.from_uci(result.move))
    return GoatMove(uci=result.move, san=san, tags=result.tags), analysis


def _state_response(
    game: Game,
    goat_move: GoatMove | None,
    analysis: Analysis | None,
    tutor: Assessment | None,
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
