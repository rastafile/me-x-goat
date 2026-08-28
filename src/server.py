"""HTTP endpoints and turn orchestration. No chess logic lives here -- it
calls game.py, engine.py, and persona.py and shapes their output as JSON.

Holds exactly one game in memory, in app.state: this is a local, single-user
app, not a multi-tenant service. No sessions, no auth, no game IDs.
"""

import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import chess
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.clock import Clock
from src.coach import narrate_assessment, narrate_goat_move, narrate_transition
from src.engine import Analysis, Candidate, Engine, EngineUnavailable
from src.game import Game, IllegalMove, PhaseSignature
from src.narration import DEFAULT_LANGUAGE, LANGUAGES
from src.persona import choose
from src.tutor import Assessment, assess

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# docs/week-7.md: (minutes, increment seconds) per preset -- "none" means
# no time control at all, app.state.clock stays None, and every clock
# field on GameStateResponse stays None too. No free-form input for v1.
_CLOCK_PRESETS: dict[str, tuple[int, int] | None] = {
    "none": None,
    "bullet": (1, 0),
    "blitz": (3, 2),
    "rapid": (10, 5),
    "classical": (30, 0),
}


def _now_ms() -> int:
    # Monotonic, not wall time: a system clock adjustment mid-game must
    # never shorten or lengthen anyone's remaining time.
    return int(time.monotonic() * 1000)


def _build_clock(preset: str) -> Clock | None:
    values = _CLOCK_PRESETS[preset]
    if values is None:
        return None
    minutes, increment_seconds = values
    total_ms = minutes * 60_000
    return Clock(white_ms=total_ms, black_ms=total_ms, increment_ms=increment_seconds * 1000)


def _timeout_outcome_for(game: Game, flagged_color: str) -> str:
    """FIDE's own rule: the flagged side loses, unless its opponent has
    insufficient material to deliver mate under any sequence of legal
    moves, in which case it's a draw -- python-chess already answers
    that question, no need to approximate it."""
    opponent_color = chess.BLACK if flagged_color == "white" else chess.WHITE
    board = chess.Board(game.fen)
    if board.has_insufficient_material(opponent_color):
        return "insufficient_material"
    return "timeout"

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
    clock: Literal["none", "bullet", "blitz", "rapid", "classical"] = "none"


class MoveRequest(BaseModel):
    uci: str


class TimeoutRequest(BaseModel):
    color: Literal["white", "black"]


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
    commentary: str


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
    mate_in: int | None
    game_plan: str | None
    is_over: bool
    outcome: str | None
    white_time_ms: int | None
    black_time_ms: int | None
    # True only when the *clock* ended the game -- outcome alone can't
    # disambiguate this from an ordinary, board-reached
    # "insufficient_material" draw, and /take-back's own rejection
    # (docs/week-7.md session 3) is specifically about the clock case, not
    # every game-over state (a checkmate can still be taken back).
    ended_by_timeout: bool


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
    # design.md §5: rewritten only on a structural transition (session 7 of
    # docs/week-4.md); persists across every move that doesn't trigger one.
    # Not undone on /take-back -- deliberately out of scope for now, see
    # docs/decisions.md ADR 8's "Known limitation".
    app.state.game_plan = None
    # One entry per ply ever pushed via /move (both the user's and the
    # GOAT's), kept in lockstep with game.ply_count -- (color, Assessment)
    # when the ply was actually assessed, None otherwise (the opening move
    # played from /new-game, or a move with no "after" analysis because it
    # ended the game). /take-back pops this alongside game.pop() to undo
    # whatever mistake count that ply had added.
    app.state.assessment_history = []
    # None until /new-game picks a preset other than "none" -- untimed
    # play stays completely unaffected (docs/week-7.md).
    app.state.clock = None
    # Set once a real flag-fall ends the game ("timeout" or, per FIDE,
    # "insufficient_material" when the non-flagged side can't possibly
    # mate) -- python-chess's own Termination enum has no timeout value,
    # and a clock isn't board state, so this lives here, not in game.py
    # (docs/week-7.md session 1).
    app.state.timeout_outcome = None
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
    app.state.game_plan = None
    app.state.clock = _build_clock(body.clock)
    app.state.timeout_outcome = None
    if app.state.clock is not None:
        app.state.clock.start_turn(game.turn, _now_ms())

    goat_move, analysis = None, None
    if not game.waiting_for_user:
        try:
            goat_move, analysis = _play_goat_move(
                game, app.state.engine, body.style, body.strength, app.state.language
            )
        except EngineUnavailable as exc:
            # game is freshly constructed and nothing's been pushed to it
            # yet (_play_goat_move analyses before it ever pushes), so
            # there's nothing to roll back here -- just a clear error
            # instead of a plain 500.
            raise HTTPException(
                status_code=503, detail="the chess engine is unavailable; game not started"
            ) from exc
        if app.state.clock is not None:
            # The GOAT's own opening move (user chose black) -- its
            # "thinking time" is whatever wall-clock time _play_goat_move
            # above actually took, same mechanism as every later round.
            now = _now_ms()
            app.state.clock.stop_turn(now)
            app.state.clock.start_turn(game.turn, now)  # now it's the user's turn
        app.state.assessment_history.append(None)  # opening move, not assessed
        # A single opening move can never trigger a transition (queens_off
        # needs a capture, file_opens needs every pawn off a file, and
        # pawn_endgame_begins needs non-king/pawn pieces gone -- none
        # possible on move 1), so no _detect_transition call here.

    return _state_response(
        game,
        goat_move,
        analysis,
        tutor=None,
        mistake_counts=app.state.mistake_counts,
        assessment_history=app.state.assessment_history,
        language=app.state.language,
        game_plan=app.state.game_plan,
        clock=app.state.clock,
        timeout_outcome=app.state.timeout_outcome,
    )


@app.post("/move", response_model=GameStateResponse)
def make_move(body: MoveRequest) -> GameStateResponse:
    game: Game | None = app.state.game
    if game is None:
        raise HTTPException(status_code=400, detail="no game in progress; call /new-game first")
    if app.state.timeout_outcome is not None:
        raise HTTPException(status_code=400, detail="the game already ended on time")

    # Timestamped and charged to the mover before anything else runs --
    # including move validation itself, so even the small CPU cost of
    # rejecting an illegal move is never refunded as free thinking time.
    now = _now_ms()
    mover_before = game.turn
    if app.state.clock is not None:
        if app.state.clock.is_flagged(mover_before, now):
            # The request arrived too late -- this mover had already run
            # out of time as of `now`, before their move is even looked
            # at. The move itself is never applied.
            app.state.clock.stop_turn(now)
            app.state.timeout_outcome = _timeout_outcome_for(game, mover_before)
            return _state_response(
                game,
                goat_move=None,
                analysis=None,
                tutor=None,
                mistake_counts=app.state.mistake_counts,
                assessment_history=app.state.assessment_history,
                language=app.state.language,
                game_plan=app.state.game_plan,
                clock=app.state.clock,
                timeout_outcome=app.state.timeout_outcome,
            )
        app.state.clock.stop_turn(now)

    # Capture the pre-move FEN and validate the move (cheap) before spending
    # an analyse() call (not cheap) on it -- an illegal move should never
    # reach the engine at all.
    fen_before_move = game.fen
    signature_before = game.phase_signature()
    ply_count_before = game.ply_count
    try:
        game.push(body.uci)
    except IllegalMove as exc:
        if app.state.clock is not None:
            app.state.clock.start_turn(mover_before, now)  # still their turn -- resume ticking
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if app.state.clock is not None and not game.is_over():
        app.state.clock.start_turn(game.turn, now)  # the GOAT's own thinking time, about to start

    user_color = game.user_color
    goat_move: GoatMove | None = None
    analysis: Analysis | None = None
    tutor_assessment: Assessment | None = None
    goat_color: str | None = None
    goat_assessment: Assessment | None = None

    # Every Stockfish call for this round lives in this block, and nothing
    # in it mutates assessment_history/mistake_counts/game_plan -- only
    # local variables. That's what makes the except branch below a real
    # rollback: if the engine is still unavailable after one restart+retry
    # (design.md §9), popping game back to ply_count_before undoes 100% of
    # what this request did, and nothing else needed undoing because
    # nothing else was touched yet.
    try:
        before = _analyse_with_retry(app.state.engine, fen_before_move, _movetime_ms(app.state.strength))

        if not game.is_over():
            goat_move, analysis = _play_goat_move(
                game, app.state.engine, app.state.style, app.state.strength, app.state.language
            )
            goat_color = "black" if user_color == "white" else "white"
            if app.state.clock is not None:
                goat_now = _now_ms()
                app.state.clock.stop_turn(goat_now)  # charges the GOAT's real analysis time
                if app.state.clock.is_flagged(goat_color, goat_now):
                    # Vanishingly unlikely at today's analysis times
                    # (50-800ms/move), but a real edge case worth handling
                    # correctly: the GOAT never actually finished this
                    # move in time, so it's undone rather than left
                    # standing next to a "time forfeit" outcome.
                    game.pop()
                    app.state.timeout_outcome = _timeout_outcome_for(game, goat_color)
                    goat_move, analysis, goat_color = None, None, None
                elif not game.is_over():
                    app.state.clock.start_turn(game.turn, goat_now)  # the user's turn again

        # analysis is the opponent's analysis of the position the user's
        # move left behind -- exactly the "after" half tutor.assess needs,
        # already paid for by _play_goat_move above. None only when the
        # user's own move ended the game, and there's nothing left to
        # analyse.
        if analysis is not None:
            tutor_assessment = assess(before, body.uci, analysis, user_color)

        # The GOAT's own move gets the same treatment, for the "both sides"
        # mistake count design.md asks for -- tutor.assess doesn't care
        # whose move it classifies (ADR 4), so this is a policy choice, not
        # a design change. Costs one further analyse() call, on the
        # position after the GOAT's own reply.
        if goat_move is not None:
            goat_color = "black" if user_color == "white" else "white"
            if not game.is_over():
                after_goat = _analyse_with_retry(app.state.engine, game.fen, _movetime_ms(app.state.strength))
                goat_assessment = assess(analysis, goat_move.uci, after_goat, goat_color)
    except EngineUnavailable as exc:
        while game.ply_count > ply_count_before:
            game.pop()
        if app.state.clock is not None:
            # Full rollback to ply_count_before -- "your move was not
            # applied" means no one should be charged for this attempt
            # either, regardless of which analyse() call inside this block
            # actually failed. The user's turn resumes now.
            app.state.clock.start_turn(mover_before, _now_ms())
        raise HTTPException(
            status_code=503, detail="the chess engine is unavailable; your move was not applied"
        ) from exc

    _track_assessment(app.state.assessment_history, app.state.mistake_counts, user_color, tutor_assessment)
    if goat_move is not None:
        _track_assessment(app.state.assessment_history, app.state.mistake_counts, goat_color, goat_assessment)

    # Diffs the whole round (user's move plus the GOAT's reply, or just the
    # user's move if it ended the game) against the position before it --
    # one plan update per round at most, per design.md §5 ("rewritten only
    # when the nature of the position changes"). Only one entry's worth
    # of history is unrolled here, so game.phase_signature() (not
    # server.py) is what actually touches the board -- see ADR 8.
    transition = _detect_transition(signature_before, game.phase_signature())
    if transition is not None:
        app.state.game_plan = narrate_transition(transition, app.state.language)

    return _state_response(
        game,
        goat_move,
        analysis,
        tutor_assessment,
        mistake_counts=app.state.mistake_counts,
        assessment_history=app.state.assessment_history,
        language=app.state.language,
        game_plan=app.state.game_plan,
        clock=app.state.clock,
        timeout_outcome=app.state.timeout_outcome,
    )


@app.post("/take-back", response_model=GameStateResponse)
def take_back() -> GameStateResponse:
    game: Game | None = app.state.game
    if game is None:
        raise HTTPException(status_code=400, detail="no game in progress; call /new-game first")
    if app.state.timeout_outcome is not None:
        # Unlike a checkmate (where popping the mating move returns to a
        # normal, playable position), there's no position to return to
        # here -- the clock, not the board, ended the game, and this
        # session doesn't invent a rule for restoring time. Reconsider if
        # this turns out to matter in practice.
        raise HTTPException(status_code=400, detail="the game already ended on time")

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

    if app.state.clock is not None and not game.is_over():
        # The clock only ever moves forward -- remaining_ms for the popped
        # plies stays exactly as deducted, never refunded (docs/week-7.md).
        # This restarts *tracking* for whoever is now to move, the same
        # way any other move leaving the game in-progress does; without
        # it, a game taken back after ending (e.g. undoing a checkmate)
        # would leave the clock frozen with no turn running at all, and
        # the mover's next real move would go uncharged entirely.
        app.state.clock.start_turn(game.turn, _now_ms())

    return _state_response(
        game,
        goat_move=None,
        analysis=None,
        tutor=None,
        mistake_counts=app.state.mistake_counts,
        assessment_history=app.state.assessment_history,
        language=app.state.language,
        game_plan=app.state.game_plan,
        clock=app.state.clock,
        timeout_outcome=app.state.timeout_outcome,
    )


@app.post("/timeout", response_model=GameStateResponse)
def timeout(body: TimeoutRequest) -> GameStateResponse:
    """Called by the client when its own local countdown display reaches
    zero (docs/week-7.md session 1). The server never trusts that claim
    directly -- it recomputes real elapsed time itself via Clock.is_flagged.
    A false alarm (client-side drift firing early, no time control this
    game, or the game already over) is a harmless no-op, not an error: a
    race here is expected, not exceptional."""
    game: Game | None = app.state.game
    if game is None:
        raise HTTPException(status_code=400, detail="no game in progress; call /new-game first")

    if (
        app.state.clock is not None
        and app.state.timeout_outcome is None
        and app.state.clock.is_flagged(body.color, _now_ms())
    ):
        app.state.clock.stop_turn(_now_ms())
        app.state.timeout_outcome = _timeout_outcome_for(game, body.color)

    return _state_response(
        game,
        goat_move=None,
        analysis=None,
        tutor=None,
        mistake_counts=app.state.mistake_counts,
        assessment_history=app.state.assessment_history,
        language=app.state.language,
        game_plan=app.state.game_plan,
        clock=app.state.clock,
        timeout_outcome=app.state.timeout_outcome,
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
    analysis = _analyse_with_retry(engine, game.fen, _movetime_ms(strength))
    board_before = chess.Board(game.fen)
    result = choose(
        game.fen, analysis.candidates, style=style, strength=strength, move_history=game.move_history()
    )
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
    is_over: bool,
    assessment_history: list[tuple[str, Assessment] | None],
    mistake_counts: dict[str, dict[str, int]],
) -> SummaryResponse | None:
    """Recomputed from assessment_history on demand rather than tracked
    incrementally: take-back already pops that history in lockstep with
    game.pop(), so recomputing "the worst ply so far" from whatever is
    actually left there is correct for free, including across repeated
    take-backs -- no separate undo logic needed for this.

    `is_over` is the caller's already-combined game.is_over() OR a real
    timeout (docs/week-7.md session 1) -- the summary is exactly as
    relevant to a game a clock ended as one the board itself ended."""
    if not is_over:
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
    language: str,
    game_plan: str | None,
    clock: Clock | None,
    timeout_outcome: str | None,
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
            commentary=narrate_assessment(tutor, language),
        )

    # A clock ending the game is not something game.py's board can express
    # (python-chess's Termination enum has no timeout value) -- combined
    # here, at the one place both are known, rather than have every caller
    # remember to OR them together itself.
    is_over = game.is_over() or timeout_outcome is not None
    outcome = timeout_outcome if timeout_outcome is not None else game.outcome()

    return GameStateResponse(
        fen=game.fen,
        user_color=game.user_color,
        legal_moves=game.legal_moves(),
        goat_move=goat_move,
        tutor=tutor_response,
        mistake_counts=mistake_counts,
        summary=_summary(is_over, assessment_history, mistake_counts),
        evaluation=_evaluation_for_user(top_candidate, game.user_color),
        mate_in=_mate_in_for_user(top_candidate, game.user_color),
        game_plan=game_plan,
        is_over=is_over,
        outcome=outcome,
        white_time_ms=clock.remaining_ms("white") if clock is not None else None,
        black_time_ms=clock.remaining_ms("black") if clock is not None else None,
        ended_by_timeout=timeout_outcome is not None,
    )


def _evaluation_for_user(candidate: Candidate | None, user_color: str) -> int | None:
    if candidate is None or candidate.score_cp is None:
        return None
    return candidate.score_cp if user_color == "white" else -candidate.score_cp


# Priority when more than one fires in the same round (rare -- e.g. the
# last non-king/pawn piece trade also happens to open a file). One plan
# update per round, per design.md §5 ("rewritten only when..."), so pick
# whichever is structurally the biggest deal.
_TRANSITION_PRIORITY = ("pawn_endgame_begins", "queens_off", "file_opens")


def _detect_transition(before: PhaseSignature, after: PhaseSignature) -> str | None:
    """Which of design.md §5's game-plan triggers fired between two
    snapshots, if any. Pure orchestration over facts game.py already
    computed (plain ints/frozensets) -- this never touches python-chess or
    a board directly, so it doesn't break "no chess logic lives here"
    (docs/decisions.md ADR 8)."""
    fired = set()
    if not before.is_pawn_endgame and after.is_pawn_endgame:
        fired.add("pawn_endgame_begins")
    if after.queens_on_board < before.queens_on_board:
        fired.add("queens_off")
    if after.open_files - before.open_files:
        fired.add("file_opens")

    for transition in _TRANSITION_PRIORITY:
        if transition in fired:
            return transition
    return None


def _analyse_with_retry(engine: Engine, fen: str, movetime_ms: int) -> Analysis:
    """design.md §9's error-handling table: 'Stockfish crashes mid-game ->
    restart the process and retry the analysis once. If it persists, warn
    and pause.' The restart itself is Engine.restart()'s job (engine.py is
    "the only boundary with Stockfish"); this is just the retry-once
    policy, and it's pure -- any object with .analyse()/.restart() works,
    so it's testable without a real subprocess. A second EngineUnavailable
    propagates; callers are responsible for turning that into a clear
    client-facing error and leaving no partially-applied state (make_move
    pops back to ply_count_before)."""
    try:
        return engine.analyse(fen, movetime_ms=movetime_ms)
    except EngineUnavailable:
        engine.restart()
        return engine.analyse(fen, movetime_ms=movetime_ms)


def _mate_in_for_user(candidate: Candidate | None, user_color: str) -> int | None:
    """Positive: the user has the mate. Negative: the user is facing it.
    Same flip convention as _evaluation_for_user, same top_candidate (the
    same analysis already paid for) -- design.md §7's badge, no extra
    Stockfish call."""
    if candidate is None or candidate.mate_in is None:
        return None
    return candidate.mate_in if user_color == "white" else -candidate.mate_in


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
