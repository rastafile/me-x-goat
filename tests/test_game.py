import pytest

from src.game import Game, IllegalMove


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


def test_black_user_starts_not_waiting_for_user():
    game = Game(user_color="black")

    assert game.waiting_for_user is False
    assert game.turn == "white"


def test_white_user_starts_waiting_for_user():
    game = Game(user_color="white")

    assert game.waiting_for_user is True


def test_random_user_color_resolves_and_stays_fixed():
    game = Game(user_color="random")

    assert game.user_color in ("white", "black")

    resolved = game.user_color
    game.push(game.legal_moves()[0])

    assert game.user_color == resolved
