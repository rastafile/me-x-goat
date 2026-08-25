"""Minimal terminal glue proving engine.py, game.py, and persona.py talk to
each other. Not worth polishing -- it disappears in week 2 when the browser
arrives.
"""

import os

import chess

from src.engine import Engine, EngineUnavailable
from src.game import Game, IllegalMove
from src.persona import choose

_STYLE = "carlsen"
_STRENGTH = 1400
_MOVETIME_MS = 200


def main() -> None:
    user_color = _ask_color()
    game = Game(user_color=user_color)
    print(f"You are playing {game.user_color}.")

    try:
        engine = Engine(path=os.environ.get("STOCKFISH_PATH", "stockfish"))
    except EngineUnavailable:
        print("Stockfish not found. Install it and try again:")
        print("  macOS:  brew install stockfish")
        print("  Debian: sudo apt install stockfish")
        return

    with engine:
        while not game.is_over():
            _print_board(game)
            if game.waiting_for_user:
                _prompt_and_push_user_move(game)
            else:
                _play_goat_move(game, engine)

    _print_board(game)
    print(f"Game over: {game.outcome()}")
    print()
    print(game.pgn())


def _ask_color() -> str:
    while True:
        raw = input("Play as white, black, or random? ").strip().lower()
        if raw in ("white", "black", "random"):
            return raw
        print("Please answer white, black, or random.")


def _print_board(game: Game) -> None:
    board = chess.Board(game.fen)
    orientation = chess.WHITE if game.user_color == "white" else chess.BLACK
    print(board.unicode(borders=True, orientation=orientation))


def _prompt_and_push_user_move(game: Game) -> None:
    while True:
        raw = input("Your move (UCI, e.g. e2e4): ").strip().lower()
        raw = _normalize_promotion(game, raw)
        board_before = chess.Board(game.fen)
        try:
            game.push(raw)
        except IllegalMove:
            print("Illegal move, try again.")
            continue
        print(f"You played {board_before.san(chess.Move.from_uci(raw))}.")
        return


def _normalize_promotion(game: Game, raw: str) -> str:
    # The terminal doesn't ask which piece; assume queen, per docs/week-1.md.
    if len(raw) != 4 or raw[3] not in ("1", "8"):
        return raw
    board = chess.Board(game.fen)
    try:
        from_square = chess.parse_square(raw[:2])
    except ValueError:
        return raw
    piece = board.piece_at(from_square)
    if piece is not None and piece.piece_type == chess.PAWN:
        return raw + "q"
    return raw


def _play_goat_move(game: Game, engine: Engine) -> None:
    analysis = engine.analyse(game.fen, movetime_ms=_MOVETIME_MS)
    choice = choose(game.fen, analysis.candidates, style=_STYLE, strength=_STRENGTH)
    board_before = chess.Board(game.fen)
    game.push(choice.move)
    san = board_before.san(chess.Move.from_uci(choice.move))
    print(f"GOAT plays {san} [tags: {', '.join(choice.tags) or 'none'}]")


if __name__ == "__main__":
    main()
