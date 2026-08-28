"""Curated opening-book lookup. Pure function: the move history so far, the
mover's own color, and a style name in -- a book move out, or `None`. Same
shape as persona.py and tutor.py: no network, no Stockfish, no state.

CLAUDE.md invariant 1: a book move is data plus a deterministic lookup
rule, a second permitted source of candidate moves alongside Stockfish's
own -- never the language model. persona.py, the only caller, is
responsible for validating that whatever this returns is actually legal in
the current position before playing it (docs/decisions.md ADR 11).
"""

import json
from dataclasses import dataclass
from pathlib import Path

_BOOK_DIR = Path(__file__).resolve().parent.parent / "data" / "opening_books"


@dataclass(frozen=True)
class _Line:
    # Which side's repertoire this line represents. A line only ever
    # answers for the color it's tagged with (ADR 11) -- the other side's
    # moves in the source game are just how that game's original opponent
    # happened to respond, not a repertoire choice worth reproducing.
    color: str
    moves: tuple[str, ...]  # UCI, the full alternating sequence from the game's start


def _load_lines(style: str) -> tuple[_Line, ...]:
    path = _BOOK_DIR / f"{style}.json"
    if not path.exists():
        return ()
    data = json.loads(path.read_text())
    return tuple(_Line(color=entry["color"], moves=tuple(entry["moves"])) for entry in data["lines"])


# Loaded once per style, the first time it's asked for -- the data is
# static for the life of the process, no reason to re-read the file on
# every move.
_books_by_style: dict[str, tuple[_Line, ...]] = {}


def next_move(move_history: list[str], color: str, style: str) -> str | None:
    """The book's answer for whoever is to move next, or None when this
    style has no book, or the game has already left every line matching
    `color`.

    Matching is an exact move-sequence prefix (docs/week-6.md session 3):
    `move_history` must equal a line's own moves up to this point,
    move-for-move -- no transposition detection. The first matching line
    wins, deterministically (persona.py stays a pure function; this must
    never pick randomly among ties).
    """
    if style not in _books_by_style:
        _books_by_style[style] = _load_lines(style)
    lines = _books_by_style[style]

    ply = len(move_history)
    for line in lines:
        if line.color != color:
            continue
        if len(line.moves) <= ply:
            continue  # this line has nothing left to say at this ply
        if tuple(move_history) == line.moves[:ply]:
            return line.moves[ply]
    return None
