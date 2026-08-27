"""Session 2 of docs/week-4.md: coach.py's GOAT voice.

No test below the `integration` mark may make a real network call -- the
Anthropic client is always mocked. The one integration test needs a real
ANTHROPIC_API_KEY and is skipped without one.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.coach import narrate_goat_move
from src.engine import Analysis, Candidate
from src.game import Game
from src.narration import describe_move
from src.persona import Choice

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _inputs() -> tuple[Analysis, Choice, Game]:
    candidate = Candidate(move="e2e4", score_cp=10, mate_in=None, pv=["e2e4"])
    analysis = Analysis(fen=START_FEN, white_to_move=True, candidates=[candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")
    return analysis, choice, game


def _fake_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_no_api_key_returns_the_grounding_text_without_calling_the_api(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    analysis, choice, game = _inputs()

    with patch("src.coach.anthropic.Anthropic") as mock_anthropic:
        result = narrate_goat_move(analysis, choice, game, "en-US")

    mock_anthropic.assert_not_called()
    assert result == describe_move(analysis, choice, game, "en-US")


def test_successful_api_call_returns_its_text_verbatim(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    analysis, choice, game = _inputs()

    with patch("src.coach.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response("Custom enriched prose.")
        mock_anthropic.return_value = mock_client

        result = narrate_goat_move(analysis, choice, game, "en-US")

    assert result == "Custom enriched prose."


def test_api_exception_falls_back_to_the_grounding_text_exactly(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    analysis, choice, game = _inputs()

    with patch("src.coach.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("network exploded")
        mock_anthropic.return_value = mock_client

        result = narrate_goat_move(analysis, choice, game, "en-US")

    assert result == describe_move(analysis, choice, game, "en-US")


def test_empty_api_response_falls_back_to_the_grounding_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    analysis, choice, game = _inputs()

    with patch("src.coach.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response("   ")
        mock_anthropic.return_value = mock_client

        result = narrate_goat_move(analysis, choice, game, "en-US")

    assert result == describe_move(analysis, choice, game, "en-US")


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs a real ANTHROPIC_API_KEY")
def test_real_api_call_returns_nonempty_prose():
    analysis, choice, game = _inputs()

    result = narrate_goat_move(analysis, choice, game, "en-US")

    assert isinstance(result, str)
    assert len(result) > 0
