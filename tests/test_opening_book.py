"""Hand-built book data only -- no PGN parsing, no Stockfish, matching
CLAUDE.md's rule that persona.py's own tests never touch either. Populates
opening_book._books_by_style directly (a private module cache) rather than
writing real files, so each test controls exactly what's in the book.
"""

from src import opening_book


def test_returns_none_for_a_style_with_no_book_file():
    assert opening_book.next_move(["e2e4"], "white", "definitely-not-a-real-style") is None


def test_returns_the_next_move_when_history_matches_a_line():
    opening_book._books_by_style["test-matches"] = (
        opening_book._Line(color="white", moves=("e2e4", "e7e5", "g1f3")),
    )

    assert opening_book.next_move(["e2e4", "e7e5"], "white", "test-matches") == "g1f3"


def test_returns_none_once_history_diverges_from_every_line():
    opening_book._books_by_style["test-diverges"] = (
        opening_book._Line(color="white", moves=("e2e4", "e7e5", "g1f3")),
    )

    assert opening_book.next_move(["d2d4"], "white", "test-diverges") is None


def test_ignores_a_line_written_for_the_other_color():
    # The other side's moves in a source game are just how that game's
    # opponent responded, not a repertoire choice for that color -- ADR 11.
    opening_book._books_by_style["test-other-color"] = (
        opening_book._Line(color="black", moves=("e2e4", "e7e5", "g1f3")),
    )

    assert opening_book.next_move(["e2e4"], "white", "test-other-color") is None


def test_returns_none_once_a_line_is_exhausted():
    opening_book._books_by_style["test-exhausted"] = (
        opening_book._Line(color="white", moves=("e2e4",)),
    )

    assert opening_book.next_move(["e2e4"], "white", "test-exhausted") is None


def test_empty_history_returns_the_lines_first_move():
    opening_book._books_by_style["test-first-move"] = (
        opening_book._Line(color="white", moves=("e2e4", "e7e5")),
    )

    assert opening_book.next_move([], "white", "test-first-move") == "e2e4"


def test_first_matching_line_wins_deterministically():
    # No randomness allowed here -- persona.py must stay a pure function.
    opening_book._books_by_style["test-first-wins"] = (
        opening_book._Line(color="white", moves=("e2e4", "e7e5", "g1f3")),
        opening_book._Line(color="white", moves=("e2e4", "e7e5", "b1c3")),
    )

    assert opening_book.next_move(["e2e4", "e7e5"], "white", "test-first-wins") == "g1f3"


def test_the_real_carlsen_book_loads_and_answers_its_first_move():
    # Confirms data/opening_books/carlsen.json actually parses -- not a
    # hand-built fixture, but this touches neither the network nor
    # Stockfish, only a local file.
    assert opening_book.next_move([], "white", "carlsen") == "g1f3"
