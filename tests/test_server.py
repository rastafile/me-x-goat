"""Sessions 1-2 of docs/week-2.md (/new-game, /move, the evaluation
perspective flip) plus sessions 2-4 of docs/week-3.md (tutor.assess wired
into /move, mistake counts both sides, the end-of-game summary) plus
sessions 1-3 of docs/week-4.md (the requested language reaching app.state;
goat_move.commentary and tutor.commentary both wired through coach.py).

Anything that spins up the app needs a real Stockfish (lifespan starts one),
so those tests are marked integration individually. _evaluation_for_user is
a pure function and is tested directly, without the app or Stockfish.
"""

import pytest
from fastapi.testclient import TestClient

from src.engine import Candidate, EngineUnavailable
from src.game import Game, PhaseSignature
from src.narration import DEFAULT_LANGUAGE
from src.server import (
    _detect_transition,
    _evaluation_for_user,
    _fresh_mistake_counts,
    _mate_in_for_user,
    _summary,
    _track_assessment,
    app,
)
from src.tutor import Assessment

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
WHITE_MATE_IN_1_FEN = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
# White to move, but already doomed -- black's rooks force mate in 1
# regardless of white's reply.
WHITE_MATED_IN_1_FEN = "K7/8/1k6/8/8/8/8/r6r w - - 0 1"
# White's queen can capture black's undefended queen on the a-file --
# queens_on_board drops from 2 to 1, firing "queens_off".
QUEEN_CAPTURE_AVAILABLE_FEN = "q3k3/8/8/8/8/8/8/Q3K3 w - - 0 1"
# Fool's mate's final position -- an already-delivered checkmate, so
# Game(fen=...).is_over() is True with zero moves needed to get there.
CHECKMATED_FEN = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
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


def test_mate_in_for_user_flips_sign_for_a_black_user():
    candidate = Candidate(move="d1h5", score_cp=None, mate_in=3, pv=["d1h5"])

    assert _mate_in_for_user(candidate, "white") == 3
    assert _mate_in_for_user(candidate, "black") == -3


def test_mate_in_for_user_is_none_for_a_cp_typed_candidate():
    candidate = Candidate(move="e2e4", score_cp=80, mate_in=None, pv=["e2e4"])

    assert _mate_in_for_user(candidate, "white") is None
    assert _mate_in_for_user(candidate, "black") is None


def test_mate_in_for_user_is_none_without_a_candidate():
    assert _mate_in_for_user(None, "white") is None


def test_evaluation_for_user_is_none_without_a_candidate():
    assert _evaluation_for_user(None, "white") is None


def _signature(queens: int = 2, open_files: frozenset[int] = frozenset(), pawn_endgame: bool = False) -> PhaseSignature:
    return PhaseSignature(queens_on_board=queens, open_files=open_files, is_pawn_endgame=pawn_endgame)


def test_detect_transition_is_none_when_nothing_changed():
    before = _signature()
    after = _signature()

    assert _detect_transition(before, after) is None


def test_detect_transition_fires_queens_off_on_any_decrease():
    before = _signature(queens=2)
    after = _signature(queens=1)

    assert _detect_transition(before, after) == "queens_off"


def test_detect_transition_does_not_fire_queens_off_when_queens_increase_or_stay():
    # Can't really increase in a real game, but the comparison itself
    # shouldn't fire on anything but a decrease.
    assert _detect_transition(_signature(queens=1), _signature(queens=1)) is None
    assert _detect_transition(_signature(queens=1), _signature(queens=2)) is None


def test_detect_transition_fires_file_opens_on_a_newly_pawnless_file():
    before = _signature(open_files=frozenset({0}))
    after = _signature(open_files=frozenset({0, 4}))

    assert _detect_transition(before, after) == "file_opens"


def test_detect_transition_fires_pawn_endgame_begins_on_the_first_entry():
    before = _signature(pawn_endgame=False)
    after = _signature(pawn_endgame=True)

    assert _detect_transition(before, after) == "pawn_endgame_begins"


def test_detect_transition_does_not_refire_pawn_endgame_once_already_in_one():
    before = _signature(pawn_endgame=True)
    after = _signature(pawn_endgame=True)

    assert _detect_transition(before, after) is None


def test_detect_transition_prioritizes_pawn_endgame_over_queens_off_and_file_opens():
    before = _signature(queens=1, open_files=frozenset(), pawn_endgame=False)
    after = _signature(queens=0, open_files=frozenset({4}), pawn_endgame=True)

    assert _detect_transition(before, after) == "pawn_endgame_begins"
    assert _evaluation_for_user(None, "black") is None


def test_track_assessment_increments_the_right_color_and_tier():
    # A hand-built Assessment isolates this from needing a real GOAT move to
    # actually blunder -- tutor.assess doesn't care whose move it classifies
    # (ADR 4), and neither does this: color is just a parameter.
    history = []
    counts = _fresh_mistake_counts()
    blunder = Assessment(
        classification="blunder", loss_cp=500, best_move="e2e4", continuation=["e2e4"], offer_take_back=True
    )

    _track_assessment(history, counts, "black", blunder)

    assert counts["black"]["blunder"] == 1
    assert counts["white"] == {"inaccuracy": 0, "mistake": 0, "blunder": 0}
    assert history == [("black", blunder)]


def test_track_assessment_with_none_appends_a_placeholder_and_counts_nothing():
    history = []
    counts = _fresh_mistake_counts()

    _track_assessment(history, counts, "white", None)

    assert history == [None]
    assert counts == _fresh_mistake_counts()


def test_track_assessment_does_not_count_excellent_or_good():
    history = []
    counts = _fresh_mistake_counts()
    good = Assessment(classification="good", loss_cp=20, best_move=None, continuation=[], offer_take_back=False)

    _track_assessment(history, counts, "white", good)

    assert counts == _fresh_mistake_counts()
    assert history == [("white", good)]


def test_summary_is_none_while_the_game_is_still_in_progress():
    game = Game(fen=START_FEN)
    counts = _fresh_mistake_counts()
    blunder = Assessment(
        classification="blunder", loss_cp=500, best_move="e2e4", continuation=["e2e4"], offer_take_back=True
    )

    assert _summary(game, [("white", blunder)], counts) is None


def test_summary_names_the_ply_and_color_of_the_worst_move():
    # A short scripted "game" (history is hand-built, not actually played) --
    # only game.is_over() needs to be real, so a real checkmate FEN stands in.
    game = Game(fen=CHECKMATED_FEN)
    counts = _fresh_mistake_counts()
    history = [
        ("white", Assessment(classification="good", loss_cp=15, best_move=None, continuation=[], offer_take_back=False)),
        ("black", Assessment(classification="excellent", loss_cp=0, best_move=None, continuation=[], offer_take_back=False)),
        (
            "white",
            Assessment(
                classification="blunder", loss_cp=650, best_move="e2e4", continuation=["e2e4"], offer_take_back=True
            ),
        ),
        ("black", Assessment(classification="inaccuracy", loss_cp=60, best_move=None, continuation=[], offer_take_back=False)),
    ]

    summary = _summary(game, history, counts)

    assert summary is not None
    assert summary.decided_at_ply == 3
    assert summary.decided_by == "white"
    assert summary.loss_cp == 650
    assert summary.mistake_counts == counts


def test_summary_is_present_even_in_a_clean_game_with_no_move_above_good():
    # There is always a worst move, even when nothing was ever a mistake --
    # the summary should still name whichever small loss was the largest.
    game = Game(fen=CHECKMATED_FEN)
    counts = _fresh_mistake_counts()
    history = [
        ("white", Assessment(classification="excellent", loss_cp=0, best_move=None, continuation=[], offer_take_back=False)),
        ("black", Assessment(classification="good", loss_cp=25, best_move=None, continuation=[], offer_take_back=False)),
        ("white", Assessment(classification="excellent", loss_cp=5, best_move=None, continuation=[], offer_take_back=False)),
    ]

    summary = _summary(game, history, counts)

    assert summary is not None
    assert summary.decided_at_ply == 2
    assert summary.decided_by == "black"
    assert summary.loss_cp == 25


def test_summary_skips_untracked_plies_when_finding_the_worst_move():
    # None entries stand for untracked plies (the black-opening move, or a
    # move that ended the game with no "after" position) and must not crash
    # or be mistaken for a zero-loss move.
    game = Game(fen=CHECKMATED_FEN)
    counts = _fresh_mistake_counts()
    history = [
        None,
        ("black", Assessment(classification="mistake", loss_cp=120, best_move="e7e5", continuation=[], offer_take_back=True)),
    ]

    summary = _summary(game, history, counts)

    assert summary is not None
    assert summary.decided_at_ply == 2
    assert summary.decided_by == "black"
    assert summary.loss_cp == 120


def test_summary_is_none_when_every_ply_is_untracked():
    game = Game(fen=CHECKMATED_FEN)
    counts = _fresh_mistake_counts()

    assert _summary(game, [None, None], counts) is None


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
def test_mate_in_is_negative_when_the_user_is_left_facing_a_forced_mate(client):
    # White is already doomed no matter what it plays; after any white
    # reply, black (the GOAT here) is left with a forced mate in 1 --
    # negative for the white user, per _mate_in_for_user's convention.
    client.post("/new-game", json={"color": "white"})
    app.state.game = Game(user_color="white", fen=WHITE_MATED_IN_1_FEN)

    response = client.post("/move", json={"uci": "a8b8"})

    assert response.json()["mate_in"] is not None
    assert response.json()["mate_in"] < 0


@pytest.mark.integration
def test_game_plan_is_null_until_the_first_transition(client):
    client.post("/new-game", json={"color": "white"})

    assert client.post("/move", json={"uci": "e2e4"}).json()["game_plan"] is None


@pytest.mark.integration
def test_game_plan_updates_when_a_queen_capture_fires_queens_off(client):
    client.post("/new-game", json={"color": "white"})
    app.state.game = Game(user_color="white", fen=QUEEN_CAPTURE_AVAILABLE_FEN)

    response = client.post("/move", json={"uci": "a1a8"})

    assert response.json()["game_plan"] is not None


@pytest.mark.integration
def test_game_plan_persists_unchanged_across_a_move_with_no_transition(client):
    client.post("/new-game", json={"color": "white"})
    app.state.game = Game(user_color="white", fen=QUEEN_CAPTURE_AVAILABLE_FEN)
    first = client.post("/move", json={"uci": "a1a8"}).json()
    assert first["game_plan"] is not None

    # After Qxa8+, black's only legal replies are king moves -- no pawns
    # exist on this board at all, so no file can newly become pawnless,
    # and white's queen (still on board) rules out a pawn endgame either
    # way. Whichever legal move comes next shouldn't touch the plan text.
    next_move = first["legal_moves"][0]
    second = client.post("/move", json={"uci": next_move}).json()

    assert second["game_plan"] == first["game_plan"]


@pytest.mark.integration
def test_new_game_as_white_has_no_goat_move_yet(client):
    response = client.post("/new-game", json={"color": "white"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_color"] == "white"
    assert body["fen"] == START_FEN
    assert body["goat_move"] is None
    assert body["mistake_counts"] == {
        "white": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
        "black": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
    }


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
def test_new_game_stores_the_requested_language(client):
    client.post("/new-game", json={"color": "white", "language": "pt-BR"})

    assert app.state.language == "pt-BR"


@pytest.mark.integration
def test_new_game_falls_back_to_the_default_language_for_an_unknown_value(client):
    client.post("/new-game", json={"color": "white", "language": "fr-FR"})

    assert app.state.language == DEFAULT_LANGUAGE


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
def test_goat_move_includes_narrated_commentary(client):
    # No ANTHROPIC_API_KEY in the test environment -- this exercises
    # coach.py's degraded path (narration.py's deterministic text) through
    # the real /new-game -> /move wiring, in the requested language.
    client.post("/new-game", json={"color": "white", "language": "pt-BR"})

    response = client.post("/move", json={"uci": "e2e4"})

    commentary = response.json()["goat_move"]["commentary"]
    assert isinstance(commentary, str)
    assert commentary != ""


@pytest.mark.integration
def test_a_bad_user_move_gets_a_tutor_assessment_with_a_stronger_alternative(client):
    client.post("/new-game", json={"color": "white", "strength": 800})

    # Nh3 on move 1 is a well-known poor opening move.
    response = client.post("/move", json={"uci": "g1h3"})

    tutor = response.json()["tutor"]
    assert tutor is not None
    assert tutor["classification"] not in ("excellent", "good")
    assert tutor["best_move"] is not None


@pytest.mark.integration
def test_tutor_assessment_includes_narrated_commentary(client):
    # No ANTHROPIC_API_KEY in the test environment -- exercises coach.py's
    # degraded path (narration.describe_assessment) through the real
    # /new-game -> /move wiring, in the requested language.
    client.post("/new-game", json={"color": "white", "strength": 800, "language": "pt-BR"})

    response = client.post("/move", json={"uci": "g1h3"})

    commentary = response.json()["tutor"]["commentary"]
    assert isinstance(commentary, str)
    assert commentary != ""


@pytest.mark.integration
def test_a_good_user_move_gets_an_excellent_or_good_assessment(client):
    client.post("/new-game", json={"color": "white", "strength": 800})

    response = client.post("/move", json={"uci": "e2e4"})

    tutor = response.json()["tutor"]
    assert tutor is not None
    assert tutor["classification"] in ("excellent", "good")
    assert tutor["best_move"] is None


@pytest.mark.integration
def test_a_mistake_increments_the_right_colors_right_counter(client):
    client.post("/new-game", json={"color": "white", "strength": 800})

    response = client.post("/move", json={"uci": "g1h3"})  # a known poor move

    body = response.json()
    classification = body["tutor"]["classification"]
    assert classification in ("inaccuracy", "mistake", "blunder")
    assert body["mistake_counts"]["white"][classification] == 1
    # Nothing else moved yet.
    for tier in ("inaccuracy", "mistake", "blunder"):
        if tier != classification:
            assert body["mistake_counts"]["white"][tier] == 0


@pytest.mark.integration
def test_an_excellent_or_good_move_increments_nothing(client):
    client.post("/new-game", json={"color": "white", "strength": 800})

    response = client.post("/move", json={"uci": "e2e4"})

    counts = response.json()["mistake_counts"]
    assert counts == {
        "white": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
        "black": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
    }


@pytest.mark.integration
def test_take_back_undoes_the_mistake_count_it_added(client):
    client.post("/new-game", json={"color": "white", "strength": 800})
    move_response = client.post("/move", json={"uci": "g1h3"})
    classification = move_response.json()["tutor"]["classification"]
    assert move_response.json()["mistake_counts"]["white"][classification] >= 1

    response = client.post("/take-back")

    assert response.json()["mistake_counts"] == {
        "white": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
        "black": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
    }


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
    # No "after" analysis exists once the user's own move ends the game --
    # there's nothing left to assess against.
    assert body["tutor"] is None
    # This game's only ply is the untracked mating move itself, so there is
    # no real assessed history to summarize -- summary is correctly None.
    assert body["summary"] is None


@pytest.mark.integration
def test_summary_is_absent_mid_game(client):
    client.post("/new-game", json={"color": "white"})

    response = client.post("/move", json={"uci": "e2e4"})

    assert response.json()["summary"] is None


@pytest.mark.integration
def test_summary_appears_when_the_game_ends_with_real_prior_history(client):
    # Simulates a game that already had one assessed ply before the winning
    # move -- unlike the injected mate-in-1 fixture above, which starts a
    # "game" with no history at all -- to confirm _summary is actually wired
    # into the live response, not just correct in isolation.
    client.post("/new-game", json={"color": "white"})
    app.state.game = Game(user_color="white", fen=WHITE_MATE_IN_1_FEN)
    app.state.assessment_history = [
        ("white", Assessment(classification="good", loss_cp=15, best_move=None, continuation=[], offer_take_back=False))
    ]

    response = client.post("/move", json={"uci": "e1e8"})

    body = response.json()
    assert body["is_over"] is True
    assert body["summary"] is not None
    assert body["summary"]["decided_at_ply"] == 1
    assert body["summary"]["decided_by"] == "white"
    assert body["summary"]["loss_cp"] == 15


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
    # The GOAT's opening move was never assessed (no "before" position to
    # compare it against); popping its untracked history entry must not
    # raise or touch the counts.
    assert response.json()["mistake_counts"] == {
        "white": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
        "black": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
    }


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
