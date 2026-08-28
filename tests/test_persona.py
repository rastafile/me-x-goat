import math

import pytest

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

# King e1, pawn e3, knight f3, vs King e8, pawn d4: both e3xd4 and Nxd4 land
# on the tension square; Ke2 is the move that actually declines it.
TENSION_SQUARE_ALSO_TAKEABLE_BY_KNIGHT_FEN = "4k3/8/8/8/3p4/4PN2/8/4K3 w - - 0 1"


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


def test_all_candidates_being_long_mates_falls_back_to_the_engines_top_move():
    # A lost position: every try still runs into a forced mate against the
    # mover, none short enough for step 1 to take outright. No cp candidate
    # exists to run the heuristics on, so choose() must not crash.
    candidates = [
        Candidate(move="a1a2", score_cp=None, mate_in=-6, pv=["a1a2"]),
        Candidate(move="b1b2", score_cp=None, mate_in=-4, pv=["b1b2"]),
    ]

    choice = choose(WHITE_TO_MOVE_FEN, candidates, strength=1400)

    assert choice.move == "a1a2"
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


def test_keep_tension_does_not_fire_when_a_different_piece_takes_the_tension_pawn():
    # Regression: Nxd4 lands on the tension square, resolving it, even
    # though it isn't the pawn-takes-pawn move itself -- it must not be
    # treated as "declining" the capture.
    candidate = Candidate(move="f3d4", score_cp=50, mate_in=None, pv=["f3d4"])

    contribution, tag = persona.keep_tension(
        TENSION_SQUARE_ALSO_TAKEABLE_BY_KNIGHT_FEN, candidate, [candidate]
    )

    assert (contribution, tag) == (0.0, None)


def test_keep_tension_still_fires_for_an_unrelated_move_in_that_same_position():
    candidate = Candidate(move="e1e2", score_cp=0, mate_in=None, pv=["e1e2"])

    contribution, tag = persona.keep_tension(
        TENSION_SQUARE_ALSO_TAKEABLE_BY_KNIGHT_FEN, candidate, [candidate]
    )

    assert (contribution, tag) == (1.5, "keep_tension")


# --- avoid_chaos -------------------------------------------------------


def test_avoid_chaos_does_not_penalize_the_top_scored_candidate():
    # e2e4 (300) is the engine's actual best line in this candidate set --
    # even in a chaotic position (spread 250 > 150), the calmest option
    # available (the one closest to that best line) draws no penalty.
    candidates = [
        Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"]),
        Candidate(move="d2d4", score_cp=50, mate_in=None, pv=["d2d4"]),
    ]

    contribution, tag = persona.avoid_chaos(WHITE_TO_MOVE_FEN, candidates[0], candidates)

    assert (contribution, tag) == (0.0, None)


def test_avoid_chaos_fully_penalizes_the_most_deviated_candidate():
    # Regression for the week-6 finding: this used to penalize every
    # survivor in a chaotic position identically, so it could never change
    # which one won (0 of 3905 firings decisive in self-play data). d2d4 is
    # the full spread away from the position's best line (e2e4) -- it draws
    # the full weight as a penalty, not a shared, order-blind one.
    candidates = [
        Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"]),
        Candidate(move="d2d4", score_cp=50, mate_in=None, pv=["d2d4"]),
    ]

    contribution, tag = persona.avoid_chaos(WHITE_TO_MOVE_FEN, candidates[1], candidates)

    assert (contribution, tag) == (-1.5, "avoid_chaos")


def test_avoid_chaos_penalty_is_proportional_between_the_extremes():
    # A third candidate roughly midway between the best line (300) and the
    # worst (50) should draw roughly half the penalty, not the full amount.
    candidates = [
        Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"]),
        Candidate(move="g1f3", score_cp=175, mate_in=None, pv=["g1f3"]),
        Candidate(move="d2d4", score_cp=50, mate_in=None, pv=["d2d4"]),
    ]

    contribution, tag = persona.avoid_chaos(WHITE_TO_MOVE_FEN, candidates[1], candidates)

    assert (contribution, tag) == (-0.75, "avoid_chaos")


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


def test_avoid_chaos_can_change_which_candidate_choose_picks(monkeypatch):
    # e3d4 captures (toward_endgame, +2.5) and shares e3 as its from-square
    # with e3e4, so improve_worst_piece contributes equally to both and
    # cancels out of the comparison -- only toward_endgame and avoid_chaos
    # actually differ here. e3d4 is also the full spread away from the
    # position's best line (300 vs 140, spread 160 > 150), so with
    # avoid_chaos weighted enough to outweigh toward_endgame's pull, the
    # calmer, better-scored e3e4 wins instead.
    #
    # The weight here is chosen only to prove the mechanism can be decisive
    # at all -- independent of whatever WEIGHTS["avoid_chaos"] settles on
    # for real play. Regression for the week-6 finding that, as originally
    # written, no weight could ever make this heuristic change a choice.
    monkeypatch.setitem(persona.WEIGHTS, "avoid_chaos", 5.0)
    candidates = [
        Candidate(move="e3e4", score_cp=300, mate_in=None, pv=["e3e4"]),
        Candidate(move="e3d4", score_cp=140, mate_in=None, pv=["e3d4"]),
    ]

    choice = choose(PAWN_CAN_CAPTURE_KNIGHT_FEN, candidates, style="carlsen", strength=800)

    assert choice.move == "e3e4"
    assert choice.tags == ["improve_worst_piece"]
    assert choice.reason_score == 1.5


# --- opening book integration (docs/decisions.md ADR 11) -------------------
#
# opening_book.py's own lookup logic has its own tests (test_opening_book.py).
# These cover only how choose() uses it: monkeypatching persona.book_next_move
# directly, rather than opening_book's real data, keeps these independent of
# whatever data/opening_books/carlsen.json happens to contain.


def test_book_move_wins_over_the_heuristic_filter(monkeypatch):
    monkeypatch.setattr(persona, "book_next_move", lambda history, color, style: "e2e4")
    candidates = [Candidate(move="g1f3", score_cp=20, mate_in=None, pv=["g1f3"])]

    choice = choose(WHITE_TO_MOVE_FEN, candidates, style="carlsen", strength=1400, move_history=[])

    assert choice == Choice(move="e2e4", tags=["opening_book"], reason_score=math.inf)


def test_forced_mate_still_wins_over_a_book_move():
    # design.md #7: a forced mate must outrank a book move if one is
    # somehow available this early -- book_next_move isn't even patched
    # here, since _shortest_forced_mate returns before the book is
    # consulted at all.
    candidates = [
        Candidate(move="d1h5", score_cp=None, mate_in=2, pv=["d1h5"]),
        Candidate(move="g1f3", score_cp=40, mate_in=None, pv=["g1f3"]),
    ]

    choice = choose(WHITE_TO_MOVE_FEN, candidates, strength=800, move_history=[])

    assert choice.move == "d1h5"
    assert choice.tags == ["forced_mate"]


def test_move_history_none_skips_the_book_lookup_entirely(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("book_next_move should not be called when move_history is None")

    monkeypatch.setattr(persona, "book_next_move", _fail)
    candidates = [
        Candidate(move="e1d1", score_cp=80, mate_in=None, pv=["e1d1"]),
        Candidate(move="d4d5", score_cp=80, mate_in=None, pv=["d4d5"]),
    ]

    choice = choose(QUEENS_FACING_FEN, candidates, style="carlsen", strength=2400)  # move_history defaults to None

    assert choice.move == "d4d5"  # falls through to the normal heuristic filter, unaffected


def test_illegal_book_move_raises_instead_of_being_played(monkeypatch):
    # a1a2 is illegal in the starting position -- a1 has white's own rook,
    # a2 has white's own pawn. A malformed or transposed book entry must
    # fail loudly here, in testing, not play an illegal move in production
    # (CLAUDE.md invariant 1, docs/week-6.md session 4's contract).
    monkeypatch.setattr(persona, "book_next_move", lambda history, color, style: "a1a2")
    candidates = [Candidate(move="g1f3", score_cp=20, mate_in=None, pv=["g1f3"])]

    with pytest.raises(AssertionError):
        choose(WHITE_TO_MOVE_FEN, candidates, style="carlsen", strength=1400, move_history=[])
