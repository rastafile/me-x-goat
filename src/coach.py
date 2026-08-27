"""The only boundary with the narration API (design.md §3's component
table). Turns narration.py's deterministic text into warmer prose via the
Anthropic API, in the requested language, falling back to that same
deterministic text on any failure -- network, timeout, a missing key, a
malformed or empty response. CLAUDE.md invariant 5: no code path here may
ever block a game on network availability.

Wraps narration.py's *output*, not persona.py's or tutor.py's raw data, on
purpose -- see docs/decisions.md ADR 7. narrate_goat_move is the opponent's
voice; narrate_assessment is the tutor's; narrate_transition is the game
plan's (design.md §5).
"""

import os

import anthropic

from src.engine import Analysis
from src.game import Game
from src.narration import describe_assessment, describe_move, describe_transition
from src.persona import Choice
from src.tutor import Assessment

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
_MAX_TOKENS = 200

_LANGUAGE_NAMES = {"en-US": "English", "pt-BR": "Brazilian Portuguese"}

_GOAT_SYSTEM_PROMPT = (
    "You are voicing a chess opponent, speaking in the first person right after making a move. "
    "Rewrite the note you're given into one or two natural, engaging sentences in {language}. "
    "You may only change how it's said, never what it says: do not add a chess claim, reason, "
    "square, or move name that isn't already in the note."
)
_TUTOR_SYSTEM_PROMPT = (
    "You are a chess tutor speaking directly to the student, in the second person, right after "
    "their move. Rewrite the note you're given into natural, encouraging sentences in {language}. "
    "You may only change how it's said, never what it says: do not add a chess claim, reason, "
    "square, or move name that isn't already in the note. If the note ends in a question (an "
    "offer to take the move back), keep it as a question at the end."
)
_PLAN_SYSTEM_PROMPT = (
    "You are a chess commentator describing a shift in the character of the game to a student, "
    "in the third person, neutral and analytical -- not addressing anyone directly. Rewrite the "
    "note you're given into one or two natural sentences in {language}. You may only change how "
    "it's said, never what it says: do not add a chess claim, reason, square, or move name that "
    "isn't already in the note."
)


def narrate_goat_move(analysis: Analysis, choice: Choice, game: Game, language: str) -> str:
    """`grounding` -- narration.py's own deterministic text -- is computed
    unconditionally, and is exactly what's returned whenever the API can't
    be used, so the enriched and degraded paths always agree on the
    underlying facts, never just on style (ADR 7)."""
    grounding = describe_move(analysis, choice, game, language)
    return _narrate(grounding, language, _GOAT_SYSTEM_PROMPT)


def narrate_assessment(assessment: Assessment, language: str) -> str:
    """Same shape as narrate_goat_move, for the tutor's voice instead."""
    grounding = describe_assessment(assessment, language)
    return _narrate(grounding, language, _TUTOR_SYSTEM_PROMPT)


def narrate_transition(transition: str, language: str) -> str:
    """Same shape again, for the game plan's voice."""
    grounding = describe_transition(transition, language)
    return _narrate(grounding, language, _PLAN_SYSTEM_PROMPT)


def _narrate(grounding: str, language: str, system_prompt: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return grounding

    try:
        return _enrich(grounding, language, api_key, system_prompt)
    except Exception:
        # The one deliberately broad except in the codebase (CLAUDE.md
        # otherwise requires named domain exceptions): invariant 5 requires
        # that nothing the narration API can do -- network failure,
        # timeout, rate limit, a malformed response -- ever blocks a game.
        # coach.py is "the only boundary with the narration API" precisely
        # so this catch has exactly one place to live.
        return grounding


def _enrich(grounding: str, language: str, api_key: str, system_prompt: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt.format(language=_LANGUAGE_NAMES.get(language, "English")),
        messages=[{"role": "user", "content": f"Note: {grounding}"}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise ValueError("empty response from the narration API")
    return text
