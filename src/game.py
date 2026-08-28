"""Game state. Wraps python-chess; nothing else touches the board."""

import random
from dataclasses import dataclass

import chess
import chess.pgn


class IllegalMove(Exception):
    pass


@dataclass(frozen=True)
class PhaseSignature:
    """Structural facts about a position, not the position itself -- for
    detecting design.md §5's game-plan transitions (queens off, a file
    opens, an endgame begins) by diffing two of these. Computed here, not
    in server.py: game.py is the only module that touches the board
    (docs/decisions.md ADR 8)."""

    queens_on_board: int
    open_files: frozenset[int]  # file indices 0-7 with no pawn of either color
    is_pawn_endgame: bool  # only kings and pawns remain, for both sides


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

    @property
    def ply_count(self) -> int:
        return len(self._board.move_stack)

    def legal_moves(self) -> list[str]:
        return [move.uci() for move in self._board.legal_moves]

    def move_history(self) -> list[str]:
        """UCI moves played so far, in order -- opening_book.py matches
        against this to decide whether the game is still in book."""
        return [move.uci() for move in self._board.move_stack]

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

    def phase_signature(self) -> PhaseSignature:
        board = self._board
        queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))

        pawns = board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)
        pawn_files = {chess.square_file(square) for square in pawns}
        open_files = frozenset(file for file in range(8) if file not in pawn_files)

        non_king_pawn_pieces = [
            piece for piece in board.piece_map().values() if piece.piece_type not in (chess.KING, chess.PAWN)
        ]

        return PhaseSignature(
            queens_on_board=queens,
            open_files=open_files,
            is_pawn_endgame=not non_king_pawn_pieces,
        )
