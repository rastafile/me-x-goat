"""Game state. Wraps python-chess; nothing else touches the board."""

import random

import chess
import chess.pgn


class IllegalMove(Exception):
    pass


class Game:
    def __init__(self, user_color: str = "white", fen: str | None = None) -> None:
        if user_color == "random":
            user_color = random.choice(["white", "black"])
        if user_color not in ("white", "black"):
            raise ValueError(f"invalid user_color: {user_color!r}")

        self._user_color = user_color
        self._board = chess.Board(fen) if fen is not None else chess.Board()

    @property
    def fen(self) -> str:
        return self._board.fen()

    @property
    def turn(self) -> str:
        return "white" if self._board.turn == chess.WHITE else "black"

    @property
    def user_color(self) -> str:
        return self._user_color

    @property
    def waiting_for_user(self) -> bool:
        return self.turn == self._user_color

    def legal_moves(self) -> list[str]:
        return [move.uci() for move in self._board.legal_moves]

    def push(self, uci: str) -> None:
        try:
            move = chess.Move.from_uci(uci)
        except chess.InvalidMoveError as exc:
            raise IllegalMove(f"not a UCI move: {uci!r}") from exc
        if move not in self._board.legal_moves:
            raise IllegalMove(f"illegal move: {uci!r}")
        self._board.push(move)

    def pop(self) -> None:
        self._board.pop()

    def is_over(self) -> bool:
        # claim_draw=True: threefold repetition and the fifty-move rule are
        # draws a player may claim, not automatic like fivefold/seventyfive.
        return self._board.is_game_over(claim_draw=True)

    def outcome(self) -> str | None:
        result = self._board.outcome(claim_draw=True)
        return None if result is None else result.termination.name.lower()

    def pgn(self) -> str:
        return str(chess.pgn.Game.from_board(self._board))
