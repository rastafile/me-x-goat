"""Builds the opponent's own commentary from tags and numbers -- no model,
no network, no API. This is the degraded-mode text design.md #9 requires
when narration is unavailable; coach.py wraps this with the model in week 4
and falls back to it on failure.
"""

import math

from src.engine import Analysis
from src.game import Game
from src.persona import WEIGHTS, Choice

_MEANINGFUL_EVAL_CP = 100  # guess, calibrate alongside the other thresholds

_LEAD_PHRASES: dict[str, str] = {
    "forced_mate": "I found a forced mate.",
    "queen_trade": "I'm trading queens while I'm ahead.",
    "toward_endgame": "I'm steering this into an endgame.",
    "improve_worst_piece": "I'm improving my worst-placed piece.",
    "keep_tension": "I'm keeping the central tension rather than resolving it.",
    "avoid_chaos": "I'm steering clear of the sharpest continuation.",
}
_NO_TAG_PHRASE = "I'm just playing the strongest move I see."

_OUTCOME_PHRASES: dict[str, str] = {
    "checkmate": "Checkmate.",
    "stalemate": "That's a stalemate.",
    "insufficient_material": "Neither of us has enough material left to win.",
    "threefold_repetition": "We've repeated the position -- that's a draw.",
    "fifty_moves": "Fifty moves without a capture or pawn push -- a draw.",
}

# forced_mate isn't a style heuristic -- it overrides them in choose() -- but
# it needs to outrank everything when picking which fired tag leads.
_LEAD_WEIGHTS: dict[str, float] = {**WEIGHTS, "forced_mate": math.inf}


def describe_move(analysis: Analysis, choice: Choice, game: Game) -> str:
    """At most two lines, first person, as the opponent. `game` reflects the
    position after `choice.move` has already been applied."""
    lines = [_lead_line(choice.tags)]

    if game.is_over():
        outcome = game.outcome()
        if outcome is not None:
            lines.append(_OUTCOME_PHRASES.get(outcome, outcome))
    else:
        eval_line = _evaluation_line(analysis, choice.move, game.user_color)
        if eval_line is not None:
            lines.append(eval_line)

    return "\n".join(lines)


def _lead_line(tags: list[str]) -> str:
    if not tags:
        return _NO_TAG_PHRASE
    lead_tag = max(tags, key=lambda tag: _LEAD_WEIGHTS.get(tag, 0.0))
    return _LEAD_PHRASES[lead_tag]


def _evaluation_line(analysis: Analysis, move: str, user_color: str) -> str | None:
    chosen = next((c for c in analysis.candidates if c.move == move), None)
    if chosen is None or chosen.score_cp is None:
        return None

    user_cp = chosen.score_cp if user_color == "white" else -chosen.score_cp
    if abs(user_cp) < _MEANINGFUL_EVAL_CP:
        return None
    if user_cp > 0:
        return "You're doing well here, I have to admit."
    return "I like where I stand right now."
