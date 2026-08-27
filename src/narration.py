"""Builds the opponent's own commentary from tags and numbers -- no model,
no network, no API. This is the degraded-mode text design.md #9 requires
when narration is unavailable; coach.py wraps this with the model in week 4
and falls back to it on failure.

Every phrase table is keyed by language first, same convention as
web/i18n.js: no user-facing string lives in a single language anywhere in
this module (CLAUDE.md's language rule, closing docs/decisions.md ADR 6's
"known limitation").
"""

import math

from src.engine import Analysis
from src.game import Game
from src.persona import WEIGHTS, Choice

DEFAULT_LANGUAGE = "en-US"
LANGUAGES = ("en-US", "pt-BR")

_MEANINGFUL_EVAL_CP = 100  # guess, calibrate alongside the other thresholds

_LEAD_PHRASES: dict[str, dict[str, str]] = {
    "en-US": {
        "forced_mate": "I found a forced mate.",
        "queen_trade": "I'm trading queens while I'm ahead.",
        "toward_endgame": "I'm steering this into an endgame.",
        "improve_worst_piece": "I'm improving my worst-placed piece.",
        "keep_tension": "I'm keeping the central tension rather than resolving it.",
        "avoid_chaos": "I'm steering clear of the sharpest continuation.",
    },
    "pt-BR": {
        "forced_mate": "Encontrei um mate forçado.",
        "queen_trade": "Estou trocando as damas enquanto estou à frente.",
        "toward_endgame": "Estou conduzindo isso para um final.",
        "improve_worst_piece": "Estou melhorando minha peça pior posicionada.",
        "keep_tension": "Estou mantendo a tensão central em vez de resolvê-la.",
        "avoid_chaos": "Estou evitando a linha mais afiada.",
    },
}
_NO_TAG_PHRASE: dict[str, str] = {
    "en-US": "I'm just playing the strongest move I see.",
    "pt-BR": "Estou só jogando o lance mais forte que vejo.",
}

_OUTCOME_PHRASES: dict[str, dict[str, str]] = {
    "en-US": {
        "checkmate": "Checkmate.",
        "stalemate": "That's a stalemate.",
        "insufficient_material": "Neither of us has enough material left to win.",
        "threefold_repetition": "We've repeated the position -- that's a draw.",
        "fifty_moves": "Fifty moves without a capture or pawn push -- a draw.",
    },
    "pt-BR": {
        "checkmate": "Xeque-mate.",
        "stalemate": "Isso é um afogamento.",
        "insufficient_material": "Nenhum de nós tem material suficiente para vencer.",
        "threefold_repetition": "Repetimos a posição -- isso é empate.",
        "fifty_moves": "Cinquenta lances sem captura ou avanço de peão -- empate.",
    },
}

_POSITIVE_EVAL_PHRASE: dict[str, str] = {
    "en-US": "You're doing well here, I have to admit.",
    "pt-BR": "Você está bem aqui, tenho que admitir.",
}
_NEGATIVE_EVAL_PHRASE: dict[str, str] = {
    "en-US": "I like where I stand right now.",
    "pt-BR": "Gosto de como estou agora.",
}

# forced_mate isn't a style heuristic -- it overrides them in choose() -- but
# it needs to outrank everything when picking which fired tag leads.
_LEAD_WEIGHTS: dict[str, float] = {**WEIGHTS, "forced_mate": math.inf}


def describe_move(analysis: Analysis, choice: Choice, game: Game, language: str) -> str:
    """At most two lines, first person, as the opponent. `game` reflects the
    position after `choice.move` has already been applied. `language` falls
    back to DEFAULT_LANGUAGE when it isn't one of LANGUAGES, same rule
    web/i18n.js applies client-side."""
    lang = language if language in LANGUAGES else DEFAULT_LANGUAGE
    lines = [_lead_line(choice.tags, lang)]

    if game.is_over():
        outcome = game.outcome()
        if outcome is not None:
            lines.append(_OUTCOME_PHRASES[lang].get(outcome, outcome))
    else:
        eval_line = _evaluation_line(analysis, choice.move, game.user_color, lang)
        if eval_line is not None:
            lines.append(eval_line)

    return "\n".join(lines)


def _lead_line(tags: list[str], language: str) -> str:
    if not tags:
        return _NO_TAG_PHRASE[language]
    lead_tag = max(tags, key=lambda tag: _LEAD_WEIGHTS.get(tag, 0.0))
    return _LEAD_PHRASES[language][lead_tag]


def _evaluation_line(analysis: Analysis, move: str, user_color: str, language: str) -> str | None:
    chosen = next((c for c in analysis.candidates if c.move == move), None)
    if chosen is None or chosen.score_cp is None:
        return None

    user_cp = chosen.score_cp if user_color == "white" else -chosen.score_cp
    if abs(user_cp) < _MEANINGFUL_EVAL_CP:
        return None
    if user_cp > 0:
        return _POSITIVE_EVAL_PHRASE[language]
    return _NEGATIVE_EVAL_PHRASE[language]
