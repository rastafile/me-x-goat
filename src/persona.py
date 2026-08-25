"""Picks the opponent's move from the engine's candidates.

Pure function: candidates in, choice out. No Stockfish, no network, no state.
"""

import math
from dataclasses import dataclass

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

    # Style heuristics (session 6) all reason in centipawns; a mate longer
    # than the short-mate cutoff has no score_cp and so never competes here.
    # It is missed unless it is short enough to win outright above.
    white_to_move = board_fen.split()[1] == "w"
    scored = [c for c in candidates if c.score_cp is not None]
    survivors = _within_margin(scored, white_to_move, strength)

    best = survivors[0]
    return Choice(move=best.move, tags=[], reason_score=0.0)


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
