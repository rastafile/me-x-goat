"""Session 1 of docs/week-2.md: /new-game and /move.

The app can't even start without a real Stockfish (lifespan spins one up),
so every test here needs one -- mark the whole module integration.
"""

import pytest
from fastapi.testclient import TestClient

from src.engine import EngineUnavailable
from src.game import Game
from src.server import app

pytestmark = pytest.mark.integration

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
WHITE_MATE_IN_1_FEN = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"


@pytest.fixture
def client():
    try:
        with TestClient(app) as test_client:
            yield test_client
    except EngineUnavailable:
        pytest.skip("stockfish not installed")


def test_new_game_as_white_has_no_goat_move_yet(client):
    response = client.post("/new-game", json={"color": "white"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_color"] == "white"
    assert body["fen"] == START_FEN
    assert body["goat_move"] is None


def test_new_game_as_black_opens_with_the_goat(client):
    response = client.post("/new-game", json={"color": "black"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_color"] == "black"
    assert body["fen"] != START_FEN
    assert body["goat_move"] is not None
    assert body["goat_move"]["uci"]
    assert body["goat_move"]["san"]


def test_new_game_random_resolves_to_a_real_color(client):
    response = client.post("/new-game", json={"color": "random"})

    assert response.json()["user_color"] in ("white", "black")


def test_move_gets_a_goat_reply_and_advances_the_fen(client):
    client.post("/new-game", json={"color": "white"})

    response = client.post("/move", json={"uci": "e2e4"})

    assert response.status_code == 200
    body = response.json()
    assert body["fen"] != START_FEN
    assert body["goat_move"] is not None
    # Two plies happened: the user's e2e4 and the GOAT's reply.
    assert body["fen"].split()[1] == "w"


def test_illegal_move_is_rejected_and_state_is_untouched(client):
    client.post("/new-game", json={"color": "white"})

    bad = client.post("/move", json={"uci": "e2e5"})
    assert bad.status_code == 400

    good = client.post("/move", json={"uci": "e2e4"})
    assert good.status_code == 200
    assert good.json()["goat_move"] is not None


def test_checkmating_move_ends_the_game_with_no_goat_reply(client):
    client.post("/new-game", json={"color": "white"})
    app.state.game = Game(user_color="white", fen=WHITE_MATE_IN_1_FEN)

    response = client.post("/move", json={"uci": "e1e8"})

    assert response.status_code == 200
    body = response.json()
    assert body["is_over"] is True
    assert body["outcome"] == "checkmate"
    assert body["goat_move"] is None
