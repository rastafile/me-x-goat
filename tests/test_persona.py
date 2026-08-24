import math

from src import persona
from src.engine import Candidate
from src.persona import Choice, choose

WHITE_TO_MOVE_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
BLACK_TO_MOVE_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


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

    choice = choose(WHITE_TO_MOVE_FEN, candidates, strength=800)

    assert choice.move != "d1h5"
    assert choice.move == "g1f3"
    assert choice.tags == []


def test_plain_candidate_set_picks_the_best_by_score_cp():
    candidates = [
        Candidate(move="e2e4", score_cp=50, mate_in=None, pv=["e2e4"]),
        Candidate(move="d2d4", score_cp=30, mate_in=None, pv=["d2d4"]),
    ]

    choice = choose(WHITE_TO_MOVE_FEN, candidates)

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
