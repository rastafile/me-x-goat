import math

from src import persona
from src.engine import Candidate
from src.persona import Choice, choose

WHITE_TO_MOVE_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
BLACK_TO_MOVE_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

# King e1, Queen d4, vs King e8, Queen d5: d4d5 captures the queen (mobility
# 24), e1d1 is a quiet king move (mobility 5, the board's lowest).
QUEENS_FACING_FEN = "4k3/8/8/3q4/3Q4/8/8/4K3 w - - 0 1"

# King e1, pawn e3, vs King e8, knight d4: e3d4 captures, e3e4 is quiet.
PAWN_CAN_CAPTURE_KNIGHT_FEN = "4k3/8/8/8/3n4/4P3/8/4K3 w - - 0 1"

# King e1, pawn e4, vs King e8, pawn d5: e4d5 is the central tension capture,
# e4e5 declines it.
CENTRAL_TENSION_FEN = "4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1"


def test_short_mate_wins_outright_even_at_low_strength():
    candidates = [
        Candidate(move="d1h5", score_cp=None, mate_in=2, pv=["d1h5"]),
        Candidate(move="g1f3", score_cp=40, mate_in=None, pv=["g1f3"]),
    ]

    choice = choose(WHITE_TO_MOVE_FEN, candidates, strength=800)

    assert choice == Choice(move="d1h5", tags=["forced_mate"], reason_score=math.inf)


def test_short_mate_picks_the_fastest_among_several():
    candidates = [
        Candidate(move="a1a2", score_cp=None, mate_in=3, pv=["a1a2"]),
        Candidate(move="b1b2", score_cp=None, mate_in=1, pv=["b1b2"]),
    ]

    choice = choose(WHITE_TO_MOVE_FEN, candidates)

    assert choice.move == "b1b2"
    assert choice.tags == ["forced_mate"]


def test_mate_outside_short_range_is_not_forced():
    candidates = [
        Candidate(move="d1h5", score_cp=None, mate_in=8, pv=["d1h5"]),
        Candidate(move="g1f3", score_cp=80, mate_in=None, pv=["g1f3"]),
    ]

    choice = choose(WHITE_TO_MOVE_FEN, candidates, style="raw", strength=800)

    assert choice.move != "d1h5"
    assert choice.move == "g1f3"
    assert choice.tags == []


def test_plain_candidate_set_picks_the_best_by_score_cp():
    candidates = [
        Candidate(move="e2e4", score_cp=50, mate_in=None, pv=["e2e4"]),
        Candidate(move="d2d4", score_cp=30, mate_in=None, pv=["d2d4"]),
    ]

    choice = choose(WHITE_TO_MOVE_FEN, candidates, style="raw")

    assert choice.move == "e2e4"
    assert choice.tags == []
    assert choice.reason_score == 0.0


def test_choose_reads_white_to_move_from_the_fen():
    # score_cp is stored in White's convention; the best move for Black
    # (the mover here) holds the most negative value.
    candidates = [
        Candidate(move="e7e5", score_cp=-50, mate_in=None, pv=["e7e5"]),
        Candidate(move="a7a6", score_cp=50, mate_in=None, pv=["a7a6"]),  # far worse for Black
    ]

    choice = choose(BLACK_TO_MOVE_FEN, candidates, strength=2400)

    assert choice.move == "e7e5"


def test_margin_cp_matches_the_documented_table():
    assert persona._margin_cp(800) == 300
    assert persona._margin_cp(1200) == 180
    assert persona._margin_cp(1600) == 100
    assert persona._margin_cp(2000) == 50
    assert persona._margin_cp(2400) == 20


def test_margin_cp_clamps_outside_the_table():
    assert persona._margin_cp(500) == 300
    assert persona._margin_cp(3000) == 20


def test_within_margin_discards_a_candidate_200cp_worse_at_strength_2400():
    best = Candidate(move="e2e4", score_cp=100, mate_in=None, pv=["e2e4"])
    close = Candidate(move="d2d4", score_cp=90, mate_in=None, pv=["d2d4"])  # 10cp worse
    far = Candidate(move="a2a3", score_cp=-100, mate_in=None, pv=["a2a3"])  # 200cp worse

    survivors = persona._within_margin([best, close, far], white_to_move=True, strength=2400)

    assert survivors == [best, close]


def test_within_margin_respects_black_to_move_perspective():
    # score_cp is stored in White's convention; the best move for Black
    # (the mover here) holds the most negative value.
    best = Candidate(move="e7e5", score_cp=-100, mate_in=None, pv=["e7e5"])
    far = Candidate(move="a7a6", score_cp=100, mate_in=None, pv=["a7a6"])  # 200cp worse for Black

    survivors = persona._within_margin([best, far], white_to_move=False, strength=2400)

    assert survivors == [best]


# --- trade_queens_when_ahead -------------------------------------------


def test_trade_queens_when_ahead_fires_on_a_queen_capture_within_range():
    candidate = Candidate(move="d4d5", score_cp=80, mate_in=None, pv=["d4d5"])

    contribution, tag = persona.trade_queens_when_ahead(QUEENS_FACING_FEN, candidate, [candidate])

    assert (contribution, tag) == (3.0, "queen_trade")


def test_trade_queens_when_ahead_does_not_fire_outside_the_eval_range():
    candidate = Candidate(move="d4d5", score_cp=500, mate_in=None, pv=["d4d5"])

    contribution, tag = persona.trade_queens_when_ahead(QUEENS_FACING_FEN, candidate, [candidate])

    assert (contribution, tag) == (0.0, None)


def test_trade_queens_when_ahead_does_not_fire_on_a_non_queen_move():
    candidate = Candidate(move="e1d1", score_cp=80, mate_in=None, pv=["e1d1"])

    contribution, tag = persona.trade_queens_when_ahead(QUEENS_FACING_FEN, candidate, [candidate])

    assert (contribution, tag) == (0.0, None)


# --- toward_endgame ------------------------------------------------------


def test_toward_endgame_fires_on_a_capture():
    candidate = Candidate(move="e3d4", score_cp=200, mate_in=None, pv=["e3d4"])

    contribution, tag = persona.toward_endgame(PAWN_CAN_CAPTURE_KNIGHT_FEN, candidate, [candidate])

    assert (contribution, tag) == (2.5, "toward_endgame")


def test_toward_endgame_does_not_fire_on_a_quiet_move():
    candidate = Candidate(move="e3e4", score_cp=50, mate_in=None, pv=["e3e4"])

    contribution, tag = persona.toward_endgame(PAWN_CAN_CAPTURE_KNIGHT_FEN, candidate, [candidate])

    assert (contribution, tag) == (0.0, None)


# --- improve_worst_piece --------------------------------------------------


def test_improve_worst_piece_fires_for_the_least_mobile_piece():
    candidate = Candidate(move="e1d1", score_cp=0, mate_in=None, pv=["e1d1"])  # king, mobility 5

    contribution, tag = persona.improve_worst_piece(QUEENS_FACING_FEN, candidate, [candidate])

    assert (contribution, tag) == (1.5, "improve_worst_piece")


def test_improve_worst_piece_does_not_fire_for_a_more_mobile_piece():
    candidate = Candidate(move="d4d5", score_cp=80, mate_in=None, pv=["d4d5"])  # queen, mobility 24

    contribution, tag = persona.improve_worst_piece(QUEENS_FACING_FEN, candidate, [candidate])

    assert (contribution, tag) == (0.0, None)


# --- keep_tension ----------------------------------------------------------


def test_keep_tension_fires_when_declining_the_available_capture():
    candidate = Candidate(move="e4e5", score_cp=20, mate_in=None, pv=["e4e5"])

    contribution, tag = persona.keep_tension(CENTRAL_TENSION_FEN, candidate, [candidate])

    assert (contribution, tag) == (1.5, "keep_tension")


def test_keep_tension_does_not_fire_when_playing_the_capture_itself():
    candidate = Candidate(move="e4d5", score_cp=100, mate_in=None, pv=["e4d5"])

    contribution, tag = persona.keep_tension(CENTRAL_TENSION_FEN, candidate, [candidate])

    assert (contribution, tag) == (0.0, None)


def test_keep_tension_does_not_fire_when_no_central_pawn_tension_exists():
    # e3d4 captures a knight, not a pawn -- not the tension this heuristic means.
    candidate = Candidate(move="e3e4", score_cp=50, mate_in=None, pv=["e3e4"])

    contribution, tag = persona.keep_tension(PAWN_CAN_CAPTURE_KNIGHT_FEN, candidate, [candidate])

    assert (contribution, tag) == (0.0, None)


# --- avoid_chaos -------------------------------------------------------


def test_avoid_chaos_fires_on_a_high_spread():
    candidates = [
        Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"]),
        Candidate(move="d2d4", score_cp=50, mate_in=None, pv=["d2d4"]),
    ]

    contribution, tag = persona.avoid_chaos(WHITE_TO_MOVE_FEN, candidates[0], candidates)

    assert (contribution, tag) == (-1.0, "avoid_chaos")


def test_avoid_chaos_does_not_fire_on_a_low_spread():
    candidates = [
        Candidate(move="e2e4", score_cp=50, mate_in=None, pv=["e2e4"]),
        Candidate(move="d2d4", score_cp=30, mate_in=None, pv=["d2d4"]),
    ]

    contribution, tag = persona.avoid_chaos(WHITE_TO_MOVE_FEN, candidates[0], candidates)

    assert (contribution, tag) == (0.0, None)


# --- choose() with heuristics engaged -------------------------------------


def test_queen_trade_wins_between_two_equally_evaluated_moves():
    # Both candidates sit at +80 (within trade_queens_when_ahead's range).
    # e1d1 also picks up improve_worst_piece (the king is the least mobile
    # piece on the board), but d4d5 still wins on trade_queens_when_ahead
    # (3.0) plus toward_endgame (2.5, it's a capture) against 1.5.
    candidates = [
        Candidate(move="e1d1", score_cp=80, mate_in=None, pv=["e1d1"]),
        Candidate(move="d4d5", score_cp=80, mate_in=None, pv=["d4d5"]),
    ]

    choice = choose(QUEENS_FACING_FEN, candidates, style="carlsen", strength=2400)

    assert choice.move == "d4d5"
    assert choice.tags == ["queen_trade", "toward_endgame"]
    assert choice.reason_score == 5.5


def test_same_candidates_produce_different_choices_under_different_styles():
    candidates = [
        Candidate(move="e1d1", score_cp=80, mate_in=None, pv=["e1d1"]),
        Candidate(move="d4d5", score_cp=80, mate_in=None, pv=["d4d5"]),
    ]

    carlsen_choice = choose(QUEENS_FACING_FEN, candidates, style="carlsen", strength=2400)
    raw_choice = choose(QUEENS_FACING_FEN, candidates, style="raw", strength=2400)

    assert carlsen_choice.move == "d4d5"
    assert raw_choice.move == "e1d1"  # ties at 0.0; the best-ranked survivor wins
    assert carlsen_choice.move != raw_choice.move


def test_returned_tags_match_the_heuristics_that_actually_fired():
    candidates = [
        Candidate(move="e1d1", score_cp=80, mate_in=None, pv=["e1d1"]),
        Candidate(move="d4d5", score_cp=80, mate_in=None, pv=["d4d5"]),
    ]

    choice = choose(QUEENS_FACING_FEN, candidates, style="carlsen", strength=2400)

    for tag in choice.tags:
        assert tag in {
            "queen_trade",
            "toward_endgame",
            "improve_worst_piece",
            "keep_tension",
            "avoid_chaos",
        }
    assert choice.tags == ["queen_trade", "toward_endgame"]
