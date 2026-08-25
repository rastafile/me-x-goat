"""Sessions 1-2 of docs/week-2.md: /new-game, /move, and the evaluation
perspective flip at the output boundary.

Anything that spins up the app needs a real Stockfish (lifespan starts one),
so those tests are marked integration individually. _evaluation_for_user is
a pure function and is tested directly, without the app or Stockfish.
"""

import pytest
from fastapi.testclient import TestClient

from src.engine import Candidate, EngineUnavailable
from src.game import Game
from src.server import _evaluation_for_user, app

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
WHITE_MATE_IN_1_FEN = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
# A whole extra queen resolves to a forced mate at shallow search depth
# (evaluation would be null, correctly, but that's not what these two test) --
# a rook is enough of an edge to show up as a plain cp score instead.
WHITE_UP_A_ROOK_FEN = "1nbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQk - 0 1"
BLACK_UP_A_ROOK_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/1NBQKBNR b KQk - 0 1"


@pytest.fixture
def client():
    try:
        with TestClient(app) as test_client:
            yield test_client
    except EngineUnavailable:
        pytest.skip("stockfish not installed")


def test_evaluation_for_user_flips_sign_for_a_black_user():
    candidate = Candidate(move="e2e4", score_cp=80, mate_in=None, pv=["e2e4"])

    assert _evaluation_for_user(candidate, "white") == 80
    assert _evaluation_for_user(candidate, "black") == -80


def test_evaluation_for_user_is_none_for_a_mate_typed_candidate():
    candidate = Candidate(move="d1h5", score_cp=None, mate_in=2, pv=["d1h5"])

    assert _evaluation_for_user(candidate, "white") is None
    assert _evaluation_for_user(candidate, "black") is None


def test_evaluation_for_user_is_none_without_a_candidate():
    assert _evaluation_for_user(None, "white") is None
    assert _evaluation_for_user(None, "black") is None


@pytest.mark.integration
def test_evaluation_is_strongly_positive_when_a_white_user_is_ahead(client):
    client.post("/new-game", json={"color": "white"})
    app.state.game = Game(user_color="white", fen=WHITE_UP_A_ROOK_FEN)

    response = client.post("/move", json={"uci": "d2d4"})

    assert response.json()["evaluation"] > 300


@pytest.mark.integration
def test_evaluation_is_strongly_positive_when_a_black_user_is_ahead(client):
    client.post("/new-game", json={"color": "black"})
    app.state.game = Game(user_color="black", fen=BLACK_UP_A_ROOK_FEN)

    response = client.post("/move", json={"uci": "d7d5"})

    assert response.json()["evaluation"] > 300


@pytest.mark.integration
def test_new_game_as_white_has_no_goat_move_yet(client):
    response = client.post("/new-game", json={"color": "white"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_color"] == "white"
    assert body["fen"] == START_FEN
    assert body["goat_move"] is None


@pytest.mark.integration
def test_new_game_as_black_opens_with_the_goat(client):
    response = client.post("/new-game", json={"color": "black"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_color"] == "black"
    assert body["fen"] != START_FEN
    assert body["goat_move"] is not None
    assert body["goat_move"]["uci"]
    assert body["goat_move"]["san"]


@pytest.mark.integration
def test_new_game_random_resolves_to_a_real_color(client):
    response = client.post("/new-game", json={"color": "random"})

    assert response.json()["user_color"] in ("white", "black")


@pytest.mark.integration
def test_move_gets_a_goat_reply_and_advances_the_fen(client):
    client.post("/new-game", json={"color": "white"})

    response = client.post("/move", json={"uci": "e2e4"})

    assert response.status_code == 200
    body = response.json()
    assert body["fen"] != START_FEN
    assert body["goat_move"] is not None
    # Two plies happened: the user's e2e4 and the GOAT's reply.
    assert body["fen"].split()[1] == "w"


@pytest.mark.integration
def test_illegal_move_is_rejected_and_state_is_untouched(client):
    client.post("/new-game", json={"color": "white"})

    bad = client.post("/move", json={"uci": "e2e5"})
    assert bad.status_code == 400

    good = client.post("/move", json={"uci": "e2e4"})
    assert good.status_code == 200
    assert good.json()["goat_move"] is not None


@pytest.mark.integration
def test_checkmating_move_ends_the_game_with_no_goat_reply(client):
    client.post("/new-game", json={"color": "white"})
    app.state.game = Game(user_color="white", fen=WHITE_MATE_IN_1_FEN)

    response = client.post("/move", json={"uci": "e1e8"})

    assert response.status_code == 200
    body = response.json()
    assert body["is_over"] is True
    assert body["outcome"] == "checkmate"
    assert body["goat_move"] is None


@pytest.mark.integration
def test_take_back_after_a_normal_round_restores_the_position_before_it(client):
    client.post("/new-game", json={"color": "white"})
    client.post("/move", json={"uci": "e2e4"})

    response = client.post("/take-back")

    assert response.status_code == 200
    assert response.json()["fen"] == START_FEN


@pytest.mark.integration
def test_take_back_right_after_a_black_opening_does_not_crash(client):
    client.post("/new-game", json={"color": "black"})

    response = client.post("/take-back")

    assert response.status_code == 200
    assert response.json()["fen"] == START_FEN


@pytest.mark.integration
def test_take_back_with_nothing_played_is_rejected(client):
    client.post("/new-game", json={"color": "white"})

    response = client.post("/take-back")

    assert response.status_code == 400


@pytest.mark.integration
def test_take_back_with_no_game_in_progress_is_rejected(client):
    response = client.post("/take-back")

    assert response.status_code == 400


@pytest.mark.integration
def test_get_pgn_matches_the_games_own_pgn(client):
    client.post("/new-game", json={"color": "white"})
    client.post("/move", json={"uci": "e2e4"})

    response = client.get("/pgn")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == app.state.game.pgn()


@pytest.mark.integration
def test_get_pgn_with_no_game_in_progress_is_rejected(client):
    response = client.get("/pgn")

    assert response.status_code == 400
