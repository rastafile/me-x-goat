"""Picks the opponent's move from the engine's candidates.

Pure function: candidates in, choice out. No Stockfish, no network, no state.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

import chess

from src.engine import Candidate

_SHORT_MATE_MAX = 3  # design.md #7: the GOAT always executes mate up to here

# Starting point from docs/week-1.md, to be calibrated in week 2.
_MARGIN_TABLE = [
    (800, 300),
    (1200, 180),
    (1600, 100),
    (2000, 50),
    (2400, 20),
]

# A heuristic gets the position, the candidate it's scoring, and the full
# scored candidate set (for heuristics that reason about the group, like
# avoid_chaos). It returns a weighted contribution and a tag, or (0.0, None)
# when it doesn't fire.
Heuristic = Callable[[str, Candidate, list[Candidate]], tuple[float, str | None]]

_CENTRAL_SQUARES = {chess.D4, chess.D5, chess.E4, chess.E5}
_CHAOS_SPREAD_CP = 150  # guess: top-5 lines disagreeing by more than this is "chaotic"


def trade_queens_when_ahead(board_fen: str, candidate: Candidate, candidates: list[Candidate]) -> tuple[float, str | None]:
    board = chess.Board(board_fen)
    move = chess.Move.from_uci(candidate.move)
    trades_queens = (
        board.piece_type_at(move.from_square) == chess.QUEEN
        and board.piece_type_at(move.to_square) == chess.QUEEN
    )
    mover_cp = candidate.score_cp if board.turn == chess.WHITE else -candidate.score_cp
    if trades_queens and 20 <= mover_cp <= 150:
        return 3.0, "queen_trade"
    return 0.0, None


def toward_endgame(board_fen: str, candidate: Candidate, candidates: list[Candidate]) -> tuple[float, str | None]:
    board = chess.Board(board_fen)
    move = chess.Move.from_uci(candidate.move)
    # A capture reduces material on the board. Whether it also holds the
    # evaluation is already guaranteed: only within-margin candidates ever
    # reach a heuristic (see choose()).
    if board.is_capture(move):
        return 2.5, "toward_endgame"
    return 0.0, None


def improve_worst_piece(board_fen: str, candidate: Candidate, candidates: list[Candidate]) -> tuple[float, str | None]:
    board = chess.Board(board_fen)
    move = chess.Move.from_uci(candidate.move)
    mobility: dict[chess.Square, int] = {}
    for legal in board.legal_moves:
        mobility[legal.from_square] = mobility.get(legal.from_square, 0) + 1
    worst = min(mobility.values())
    if mobility.get(move.from_square) == worst:
        return 1.5, "improve_worst_piece"
    return 0.0, None


def keep_tension(board_fen: str, candidate: Candidate, candidates: list[Candidate]) -> tuple[float, str | None]:
    board = chess.Board(board_fen)
    move = chess.Move.from_uci(candidate.move)
    tension_captures = {
        legal
        for legal in board.legal_moves
        if board.piece_type_at(legal.from_square) == chess.PAWN
        and board.piece_type_at(legal.to_square) == chess.PAWN
        and legal.to_square in _CENTRAL_SQUARES
    }
    if tension_captures and move not in tension_captures:
        return 1.5, "keep_tension"
    return 0.0, None


def avoid_chaos(board_fen: str, candidate: Candidate, candidates: list[Candidate]) -> tuple[float, str | None]:
    board = chess.Board(board_fen)
    scores = [c.score_cp if board.turn == chess.WHITE else -c.score_cp for c in candidates]
    if len(scores) < 2:
        return 0.0, None
    if max(scores) - min(scores) > _CHAOS_SPREAD_CP:
        return -1.0, "avoid_chaos"
    return 0.0, None


_STYLES: dict[str, list[Heuristic]] = {
    "carlsen": [
        trade_queens_when_ahead,
        toward_endgame,
        improve_worst_piece,
        keep_tension,
        avoid_chaos,
    ],
    # design.md #5: "raw engine" reuses the same structure with an empty
    # weight table -- no heuristic fires, so selection falls through to
    # step 4's tie-break, the best score_cp survivor.
    "raw": [],
}


@dataclass(frozen=True)
class Choice:
    move: str
    tags: list[str]
    reason_score: float


def choose(
    board_fen: str,
    candidates: list[Candidate],
    style: str = "carlsen",
    strength: int = 1400,
) -> Choice:
    forced_mate = _shortest_forced_mate(candidates)
    if forced_mate is not None:
        return Choice(move=forced_mate.move, tags=["forced_mate"], reason_score=math.inf)

    # The heuristics all reason in centipawns; a mate longer than the
    # short-mate cutoff has no score_cp and so never competes below. It is
    # missed unless it is short enough to win outright above.
    white_to_move = board_fen.split()[1] == "w"
    scored = [c for c in candidates if c.score_cp is not None]
    survivors = _within_margin(scored, white_to_move, strength)

    heuristics = _STYLES[style]
    best_total: float | None = None
    best_candidate: Candidate | None = None
    best_tags: list[str] = []
    for candidate in survivors:
        total = 0.0
        tags: list[str] = []
        for heuristic in heuristics:
            contribution, tag = heuristic(board_fen, candidate, scored)
            total += contribution
            if tag is not None:
                tags.append(tag)
        # Strict >: survivors is already best-to-worst by score_cp, so a tie
        # never displaces an earlier candidate -- step 4's tie-break for free.
        if best_total is None or total > best_total:
            best_total, best_candidate, best_tags = total, candidate, tags

    return Choice(move=best_candidate.move, tags=best_tags, reason_score=best_total)


def _shortest_forced_mate(candidates: list[Candidate]) -> Candidate | None:
    forced = [c for c in candidates if c.mate_in is not None and 1 <= c.mate_in <= _SHORT_MATE_MAX]
    return min(forced, key=lambda c: c.mate_in, default=None)


def _within_margin(scored: list[Candidate], white_to_move: bool, strength: int) -> list[Candidate]:
    margin = _margin_cp(strength)
    best_mover_cp = _mover_cp(scored[0], white_to_move)
    return [c for c in scored if best_mover_cp - _mover_cp(c, white_to_move) <= margin]


def _mover_cp(candidate: Candidate, white_to_move: bool) -> int:
    return candidate.score_cp if white_to_move else -candidate.score_cp


def _margin_cp(strength: int) -> int:
    if strength <= _MARGIN_TABLE[0][0]:
        return _MARGIN_TABLE[0][1]
    if strength >= _MARGIN_TABLE[-1][0]:
        return _MARGIN_TABLE[-1][1]
    for (lo_strength, lo_margin), (hi_strength, hi_margin) in zip(_MARGIN_TABLE, _MARGIN_TABLE[1:]):
        if lo_strength <= strength <= hi_strength:
            t = (strength - lo_strength) / (hi_strength - lo_strength)
            return round(lo_margin + t * (hi_margin - lo_margin))
    raise AssertionError("unreachable: strength is clamped to the table's range above")
