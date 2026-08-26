"""Classifies the user's move. Pure function: no Stockfish, no network, no
state, no access to persona.py (docs/decisions.md ADR 4).
"""

from dataclasses import dataclass

from src.engine import Analysis, mover_score

_THRESHOLDS = [
    (10, "excellent"),
    (50, "good"),
    (100, "inaccuracy"),
    (300, "mistake"),
]  # anything above the last bound is "blunder". Guess now, calibrate later,
# same spirit as persona.py's margin table and avoid_chaos's spread threshold.

_CONTINUATION_LENGTH = 4


@dataclass(frozen=True)
class Assessment:
    classification: str
    loss_cp: int
    best_move: str | None
    continuation: list[str]
    offer_take_back: bool


def loss_cp(before: Analysis, after: Analysis, mover_color: str) -> int:
    """How much worse the actual result is than the best available, from the
    mover's point of view. Needs both sides of the move: `before` is the
    mover's own analysis of the position they faced; `after` is the
    opponent's analysis of the position the move left behind. This is not
    the same computation as Analysis.loss_cp, which only ranks candidates
    within a single analysis -- the move actually played is frequently not
    among either side's top candidates at all.
    """
    mover_is_white = mover_color == "white"
    best_available = mover_score(before.candidates[0], mover_is_white)
    # after.candidates[0] is the opponent's own best line, in their own
    # perspective; negate it to read the resulting position from the
    # original mover's side instead (a zero-sum flip, not another
    # White/Black convention flip).
    actual_result = -mover_score(after.candidates[0], after.white_to_move)
    return max(0, best_available - actual_result)


def classify(loss: int) -> str:
    for bound, label in _THRESHOLDS:
        if loss <= bound:
            return label
    return "blunder"


def assess(before: Analysis, move: str, after: Analysis, mover_color: str) -> Assessment:
    loss = loss_cp(before, after, mover_color)
    classification = classify(loss)

    if classification in ("excellent", "good"):
        # Asymmetric commentary, at the data level: nothing here for
        # coach.py (week 4) to elaborate on, the same way persona.choose
        # returns empty tags when no heuristic fires.
        return Assessment(
            classification=classification,
            loss_cp=loss,
            best_move=None,
            continuation=[],
            offer_take_back=False,
        )

    best = before.candidates[0]
    return Assessment(
        classification=classification,
        loss_cp=loss,
        best_move=best.move,
        continuation=best.pv[:_CONTINUATION_LENGTH],
        offer_take_back=classification == "blunder",
    )
