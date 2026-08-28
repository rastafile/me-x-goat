import pytest

from src.game import Game, IllegalMove

# Pawns removed from the d- and e-files for both colors (back ranks and
# every other pawn untouched) -- isolates open_files from the other two
# phase_signature facts, which stay unchanged from the start position.
OPEN_D_AND_E_FILES_FEN = "rnbqkbnr/ppp2ppp/8/8/8/8/PPP2PPP/RNBQKBNR w KQkq - 0 1"
# Only kings and e-pawns -- a pure king-and-pawn endgame, no queens, and
# every file but e is open.
KING_AND_PAWN_ENDGAME_FEN = "4k3/4p3/8/8/8/8/4P3/4K3 w - - 0 1"
SINGLE_QUEEN_LEFT_FEN = "4k3/8/8/8/8/8/8/3QK3 w - - 0 1"


def test_scholars_mate_ends_in_checkmate():
    game = Game()
    for uci in ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]:
        game.push(uci)

    assert game.is_over()
    assert game.outcome() == "checkmate"


def test_stalemate_position_returns_stalemate():
    game = Game(fen="7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")

    assert game.is_over()
    assert game.outcome() == "stalemate"


def test_king_versus_king_returns_insufficient_material():
    game = Game(fen="8/8/4k3/8/8/4K3/8/8 w - - 0 1")

    assert game.is_over()
    assert game.outcome() == "insufficient_material"


def test_forced_threefold_repetition_is_detected():
    game = Game()
    shuffle = ["g1f3", "g8f6", "f3g1", "f6g8"]
    for uci in shuffle * 2:
        game.push(uci)

    assert game.is_over()
    assert game.outcome() == "threefold_repetition"


def test_illegal_move_raises_and_leaves_state_untouched():
    game = Game()
    fen_before = game.fen

    with pytest.raises(IllegalMove):
        game.push("e2e5")  # not a legal pawn move

    assert game.fen == fen_before


def test_malformed_uci_raises_illegal_move():
    game = Game()
    fen_before = game.fen

    with pytest.raises(IllegalMove):
        game.push("zzzz")

    assert game.fen == fen_before


def test_push_then_pop_restores_original_fen():
    game = Game()
    fen_before = game.fen

    game.push("e2e4")
    game.pop()

    assert game.fen == fen_before


def test_move_history_reflects_moves_played_in_order():
    game = Game()

    assert game.move_history() == []

    game.push("e2e4")
    game.push("e7e5")

    assert game.move_history() == ["e2e4", "e7e5"]


def test_move_history_shrinks_after_pop():
    game = Game()
    game.push("e2e4")
    game.push("e7e5")

    game.pop()

    assert game.move_history() == ["e2e4"]


def test_black_user_starts_not_waiting_for_user():
    game = Game(user_color="black")

    assert game.waiting_for_user is False
    assert game.turn == "white"


def test_ply_count_tracks_pushes_and_pops():
    game = Game()
    assert game.ply_count == 0

    game.push("e2e4")
    game.push("e7e5")
    assert game.ply_count == 2

    game.pop()
    assert game.ply_count == 1


def test_white_user_starts_waiting_for_user():
    game = Game(user_color="white")

    assert game.waiting_for_user is True


def test_random_user_color_resolves_and_stays_fixed():
    game = Game(user_color="random")

    assert game.user_color in ("white", "black")

    resolved = game.user_color
    game.push(game.legal_moves()[0])

    assert game.user_color == resolved


def test_phase_signature_at_the_start_has_both_queens_no_open_files_not_an_endgame():
    signature = Game().phase_signature()

    assert signature.queens_on_board == 2
    assert signature.open_files == frozenset()
    assert signature.is_pawn_endgame is False


def test_phase_signature_counts_a_single_remaining_queen():
    signature = Game(fen=SINGLE_QUEEN_LEFT_FEN).phase_signature()

    assert signature.queens_on_board == 1


def test_phase_signature_finds_every_pawnless_file():
    signature = Game(fen=OPEN_D_AND_E_FILES_FEN).phase_signature()

    assert signature.open_files == frozenset({3, 4})  # d and e


def test_phase_signature_recognizes_a_king_and_pawn_endgame():
    signature = Game(fen=KING_AND_PAWN_ENDGAME_FEN).phase_signature()

    assert signature.is_pawn_endgame is True
    assert signature.queens_on_board == 0


def test_phase_signature_is_not_a_pawn_endgame_with_any_other_piece_left():
    # Same shape as the start position -- plenty of non-king/pawn pieces.
    signature = Game().phase_signature()

    assert signature.is_pawn_endgame is False
