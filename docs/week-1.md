# Week 1 — implementation plan

Goal: a complete game playable in the terminal against an opponent that picks moves
with style. No interface, no server, no API.

Three modules: `engine.py`, `game.py`, `persona.py`. None of them need the network.
All of them testable in isolation.

---

## 0. Setup

```bash
brew install stockfish
stockfish            # type "uci", confirm the response, then "quit"

mkdir me-x-goat && cd me-x-goat
git init
python3 -m venv .venv && source .venv/bin/activate
pip install chess pytest
pip freeze > requirements.txt
```

Layout:

```
me-x-goat/
  src/
    __init__.py
    engine.py
    game.py
    persona.py
    play_cli.py
  tests/
    test_engine.py
    test_game.py
    test_persona.py
  docs/design.md
  docs/week-1.md
  CLAUDE.md
  README.md
  LICENSE
  requirements.txt
```

First commit is README and LICENSE, before any code.

---

## 1. `engine.py`

The only module that talks to Stockfish. Everything else consumes its output.

### Contract

```python
@dataclass(frozen=True)
class Candidate:
    move: str               # UCI, e.g. "e2e4"
    score_cp: int | None    # centipawns, normalized to White's perspective
    mate_in: int | None     # moves to mate; negative means being mated
    pv: list[str]           # principal variation

class Engine:
    def __init__(self, path: str = "stockfish", multipv: int = 5): ...
    def analyse(self, fen: str, movetime_ms: int) -> list[Candidate]: ...
    def close(self) -> None: ...
```

`analyse` returns the list sorted best to worst. Exactly one of `score_cp` and
`mate_in` is populated.

### Known traps

**Scores come from the side to move, not from White.** Stockfish returns `+50` for
whoever is on move. Comparing consecutive evaluations without flipping the sign is
the classic bug, and it produces a tutor that praises your mistakes with total
confidence. Normalize to White's perspective inside `engine.py` and never think about
it again.

**Perspective is an internal convention, not a display one.** Normalizing to White is
correct internally, but the screen must show numbers from the user's point of view. A
`+80` for White is a disadvantage for a user playing Black. The flip happens in one
place, at the output boundary — never scattered across modules.

**`mate` is not `cp`.** Stockfish returns either `score mate 3` or `score cp 42`,
never both. Treating mate as a very large centipawn value works almost always, and
fails exactly when it matters.

**MultiPV is an option, not a parameter.** `setoption name MultiPV value 5` must be
sent before `go`, and it persists until changed.

**`info` lines repeat.** Every depth re-emits all variations. Only the last set before
`bestmove` counts — store by PV index, overwriting as they arrive.

**The process must be killed.** Without `close()`, Stockfish is orphaned and burns
CPU. Use a context manager.

Note: `python-chess` ships `chess.engine.SimpleEngine`, which handles all of the
above. Use it. Writing the raw UCI dialogue once, to understand it, and then
switching to the library is a good path.

### Tests

- Starting position returns 5 candidates, all legal.
- A mate-in-1 position returns `mate_in == 1` on the first candidate.
- A position with forced mate against returns a negative `mate_in`.
- Perspective: the same position with White to move and with Black to move produces
  consistent signs after normalization.
- `close()` terminates the process.

---

## 2. `game.py`

Game state. Wraps `python-chess` and stops anyone else from touching the board.

### Contract

```python
class Game:
    def __init__(self, user_color: str = "white", fen: str | None = None): ...
    # user_color: "white" | "black" | "random"; "random" is resolved in __init__

    @property
    def fen(self) -> str: ...
    @property
    def turn(self) -> str: ...              # "white" | "black"
    @property
    def user_color(self) -> str: ...        # resolved, never "random"
    @property
    def waiting_for_user(self) -> bool: ... # False when it is the opponent's turn

    def legal_moves(self) -> list[str]:     # UCI
    def push(self, uci: str) -> None:       # raises IllegalMove
    def pop(self) -> None:                  # undo
    def is_over(self) -> bool: ...
    def outcome(self) -> str | None:        # "checkmate" | "stalemate" | ...
    def pgn(self) -> str: ...
```

### Care points

Promotion arrives in UCI as a fifth character (`e7e8q`). The interface must ask which
piece; in the terminal, assume queen and move on.

`pop()` exists from day one because taking back moves is a product requirement, not an
extra. With the user playing Black, undo removes two plies, not one: the user's move
and the opponent's reply. Make that explicit in the contract now.

`user_color` decides who opens. With the user on Black, the first `push` of the game
belongs to the opponent. `waiting_for_user` exists so the main loop never has to infer
this by comparing colors.

Game end covers five cases: checkmate, stalemate, threefold repetition, the fifty-move
rule, and insufficient material. All come free from `python-chess` — the work is
exposing each one by name, because the tutor will want to explain which one happened.

### Tests

- Scholar's mate sequence ends in `checkmate`.
- A classic stalemate position returns `stalemate`.
- King versus king returns insufficient material.
- Forced threefold repetition is detected.
- An illegal move raises and leaves the state untouched.
- `push` followed by `pop` restores the original FEN.
- A game with `user_color="black"` starts with `waiting_for_user` as `False`.
- `user_color="random"` resolves to white or black and does not change afterwards.

---

## 3. `persona.py`

The heart of the project. A pure function: candidates in, choice out. No Stockfish, no
network, no state.

### Contract

```python
@dataclass(frozen=True)
class Choice:
    move: str
    tags: list[str]
    reason_score: float

def choose(
    board_fen: str,
    candidates: list[Candidate],
    style: str = "carlsen",
    strength: int = 1400,
) -> Choice: ...
```

### Algorithm

1. **Short mate wins outright.** If any candidate has `mate_in` between 1 and 3, take
   it immediately with the tag `forced_mate`. This holds at every strength level — see
   spec, section 7.
2. **Tolerance margin.** Derived from `strength`. Discard any candidate more than N
   centipawns below the best.
3. **Style scoring.** Each heuristic receives the position and the move, and returns a
   numeric contribution plus a tag when it fires.
4. **Selection.** Highest total score. Ties broken by best `score_cp`.

### Carlsen heuristics

| Function | Fires when | Tag | Initial weight |
|---|---|---|---|
| `trade_queens_when_ahead` | the move trades queens and the evaluation sits between +20 and +150 | `queen_trade` | 3.0 |
| `toward_endgame` | reduces total material without losing evaluation | `toward_endgame` | 2.5 |
| `improve_worst_piece` | moves the piece with the lowest mobility on the board | `improve_worst_piece` | 1.5 |
| `keep_tension` | declines an available central pawn capture | `keep_tension` | 1.5 |
| `avoid_chaos` | penalizes high variance across the five candidates | `avoid_chaos` | 1.0 |

Initial weights are guesses. They get calibrated in week 2.

Each heuristic is an isolated function, testable against a hand-built position. None
of them knows about the others.

### Margin by strength

Starting point, to be calibrated:

| Strength | Margin (cp) | Analysis time |
|---|---|---|
| 800 | 300 | 50 ms |
| 1200 | 180 | 100 ms |
| 1600 | 100 | 200 ms |
| 2000 | 50 | 400 ms |
| 2400+ | 20 | 800 ms |

### Tests

All with hand-built candidates, no Stockfish:

- Mate in 2 available: chosen even at strength 800.
- Mate in 8 available at strength 800: not required to be chosen.
- Two moves with identical evaluation, one trading queens while ahead: the trade wins.
- A candidate 200 cp worse at strength 2400: discarded.
- The same candidate set under different styles produces different choices.
- Returned tags match the heuristics that actually fired.

---

## 4. `play_cli.py`

Minimal glue. Asks for color, prints the board as text in the right orientation, reads
a move from the keyboard, calls `persona.choose`, applies it, repeats. Prints the PGN
at the end.

If the user takes Black, the loop opens with the opponent's move.

Not worth polishing — it disappears in week 2 when the browser arrives. It exists to
prove the three modules talk to each other.

---

## 5. Work order

| Session | Build | Done when |
|---|---|---|
| 1 | Setup, repository, README, LICENSE | first commit pushed |
| 2 | `engine.py` with raw UCI dialogue | terminal shows 5 candidates for a position |
| 3 | `engine.py` tests, switch to `SimpleEngine` | suite green |
| 4 | `game.py`, color selection, tests | Scholar's mate detected; a Black game opens with the opponent |
| 5 | `persona.py`: structure, short mate, margin | picks among hand-built candidates |
| 6 | The five heuristics and their tests | suite green |
| 7 | `play_cli.py` | full game played in the terminal |

Seven sessions. Fitting them into five days leaves slack for week 2, which is the
heaviest on interface work.

---

## 6. Definition of done

Two full games played in the terminal, one as White and one as Black, from first move
to result, against the styled opponent, with PGN exported at the end. Test suite green.
Public repository with a README explaining how to run it.

If that stands by Friday, posts 1 and 2 write themselves — the material already exists.

---

## 7. Not this week

- Interface, server, HTTP.
- API calls or any model-generated text.
- Weight calibration. Guess now, measure in week 2.
- Performance optimization.
- Styles beyond Carlsen. The structure already allows them; adding them now only
  widens the surface for bugs.
