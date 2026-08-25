# Me X GOAT — design document

Status: approved, implementation in progress

## 1. Vision

A local chess application running entirely on a single machine, where the user plays
against an opponent with a grandmaster persona (the "GOAT") and receives analysis
from an independent tutor after every move.

The goal is not winning games. It is understanding chess. Every design decision is
subordinate to that.

The app does not connect to Chess.com or any other online platform. It is an isolated
training tool.

## 2. Premises

- **The LLM does not play chess.** Every move choice and every numeric evaluation
  comes from Stockfish. The language model only narrates. That separation is what
  prevents illegal moves and invented evaluations.
- **Strength is adjustable.** A grandmaster at full strength teaches a beginner
  nothing. The persona keeps its style at any strength level.
- **Tutor and GOAT are independent.** The tutor analyzes the position only. It has no
  access to the GOAT's internal plan. Leaking that would destroy the game.
- **No assistance before the user's move.** The tutor speaks only after the move is
  made. The mental effort of choosing alone is where learning happens.

## 3. Architecture

Local Python server plus a browser interface on `localhost`. Nothing leaves the
machine except the narration calls.

```
browser (cm-chessboard)
        |
    local HTTP
        |
   server.py (FastAPI)
        |
   +----+----+----------+
   |         |          |
game.py  engine.py   coach.py
         (Stockfish)   (API)
             |
   +---------+---------+
   |                   |
persona.py         tutor.py
```

### Components

| Module | Responsibility | Depends on |
|---|---|---|
| `engine.py` | Speaks UCI with Stockfish. Takes a FEN, returns the N best moves with evaluation (MultiPV), distinguishing centipawn scores from distance to mate. | Stockfish |
| `persona.py` | Picks the GOAT's move from the candidates by applying style heuristics. Returns the move plus intent tags. | `engine` |
| `tutor.py` | Analyzes the move the user just played. Classifies its quality and projects the likely continuation. | `engine` |
| `coach.py` | Turns tags and numbers into natural language via the API. Two distinct voices: GOAT and tutor. | API |
| `game.py` | Game state, move validation, game-over detection, PGN export. | python-chess |
| `server.py` | HTTP endpoints and turn orchestration. | all |
| `web/` | Board, panels, themes, controls. | cm-chessboard |

Each module has a single responsibility and can be tested in isolation. `persona.py`
and `tutor.py` are pure functions over the engine's output — testable without network
and without an API key.

`web/` uses `cm-chessboard` (MIT), not chessground: chessground is GPL-3, and unlike
Stockfish's subprocess isolation, a board-rendering library runs in the same JS
runtime as the app's own frontend code — bundling it would carry the GPL into that
bundle. `cm-chessboard` is vendored directly into `web/` (its MIT license allows
that), which also keeps the board working fully offline, consistent with this app
never needing anything but the narration calls to leave the machine.

## 4. Game start and turn flow

### Color selection

Before the first move, the user picks white, black, or random. That choice determines
three things:

- who opens the game;
- board orientation, always with the user's pieces at the bottom;
- the perspective of every number shown on screen.

If the user picks black, the game opens with a GOAT move and its commentary, before
any interaction. The tutor stays silent — it only analyzes the user's moves.

A random choice is resolved on the server and announced before play begins.

### Evaluation perspective

Internally, all evaluations are normalized to White's perspective. At presentation
time they are flipped when the user plays black, so that a positive number always
means the user is better.

That conversion happens in exactly one place, at the server's output boundary. No
internal module ever handles two conventions at once.

### Turn flow

1. The user drags a piece. cm-chessboard only permits legal destinations — the
   destination list arrives with the game state.
2. `POST /move` with the move in UCI notation.
3. `game.py` validates and applies it. An illegal move returns an error and the piece
   snaps back.
4. `tutor.py` analyzes: compares evaluation before and after, classifies the move,
   identifies what was won or lost, projects three or four moves of continuation.
5. `persona.py` picks the GOAT's reply and returns intent tags.
6. `game.py` applies the GOAT's move.
7. `coach.py` generates two texts: the tutor's analysis and the GOAT's commentary.
8. A single response carries the new FEN, the GOAT's move, both texts, the updated
   plan, and the evaluation.
9. The interface animates the move and fills both panels.

The tutor's analysis and the GOAT's choice run sequentially against the same
Stockfish instance. The two narration calls are independent and run in parallel.

## 5. The GOAT persona

`persona.py` receives the five best moves with their evaluations. It discards any
that fall outside a tolerance margin. Among the rest, it scores each one against the
selected style's heuristics and picks the highest.

Carlsen-style heuristics (v1):

| Tag | Fires when | Weight |
|---|---|---|
| `trade_queens` | The move trades queens while holding a small edge | high |
| `toward_endgame` | Reduces total material without losing evaluation | high |
| `improve_worst_piece` | Moves the piece with the lowest mobility on the board | medium |
| `keep_tension` | Declines to resolve a central pawn tension | medium |
| `avoid_chaos` | Penalizes lines with high variance across candidates | medium |

Tags travel with the move all the way to `coach.py`, which uses them as raw material
for the text. This guarantees the explanation matches the actual reason for the
choice, rather than being a rationalization invented by the model.

Additional styles (Tal, Petrosian, raw engine) reuse the same structure with a
different weight table. Adding a style means adding a table, not new code.

### Strength adjustment

A single parameter (800 to 2800) controls two values:

- Stockfish analysis time per move;
- the width of the tolerance margin in centipawns.

A wide margin means choosing among moves that are good but not optimal, which lowers
strength without destroying style. Exact numbers to be calibrated during
implementation.

### Game plan

Persistent text, separate from the per-move commentary. It is rewritten only when the
nature of the position changes: queens come off, a file opens, the pawn structure
shifts, an endgame begins. `persona.py` flags those transitions; between them, the
plan stays put on screen.

## 6. The tutor

Analyzes the user's move exclusively, with no access to the GOAT's internal state.

The tutor analyzes only the user's moves, whether the user is white or black. When
the user plays black, the game's first move belongs to the GOAT and produces no
analysis.

Every number the tutor presents follows the user's perspective: gains are positive,
losses are negative, regardless of color.

Classification by evaluation loss in centipawns: excellent, good, inaccuracy,
mistake, blunder. Thresholds are configurable.

Each analysis delivers:

- what the move won or gave away, in plain language;
- what the stronger alternative would have been, and why — framed as learning, not
  as reproach;
- the likely continuation over three or four moves;
- on a blunder, an offer to take the move back, always after the explanation.

Taking moves back is freely allowed. This app has no rating and no competition.

## 7. Announced mate

Stockfish reports mate natively: instead of a centipawn evaluation, it returns the
distance to forced mate. `engine.py` distinguishes the two return types and
propagates the information.

### Display rule

A discreet badge above the board announces the **existence** of mate and its
**distance**, in both directions:

- "mate in 3 available" — when the user has the sequence;
- "you are facing mate in 2" — when the threat runs the other way.

The badge never names the piece, the square, or the move. The model is the tactics
puzzle book: the prompt tells you a solution exists and how many moves it takes, and
you go find it. Announcing that mate exists is pedagogical; showing which move it is
is not.

The solution appears only through the tutor, after the user has moved — whether they
found it or not.

The badge has its own switch. The reasoning is direct: left on indefinitely, the user
stops scanning the position for mate and starts waiting for the warning. The skill
never forms. The switch exists so they can wean themselves off it.

### Reach

Short mates (up to five or six moves) Stockfish finds instantly at any setting.
Long mates require depth that low strength levels do not reach. The badge is
therefore reliable when it appears and sometimes absent when mate is remote. It is
never wrong.

### Interaction with strength adjustment

On the GOAT's side there is a conflict: an opponent set to 1200 that executes mate in
9 with precision is incoherent with its own persona.

Adopted rule: mates up to three moves the GOAT always executes, at any strength.
Longer mates go through the same tolerance filter as any other move, and may
therefore be missed at low levels. This keeps the persona coherent — inattentive at
low strength, but not so inattentive as to miss an obvious mate.

## 8. Interface

- cm-chessboard board: drag pieces, last-move highlight, legal destinations, premove.
- Tutor panel and GOAT panel visually distinct — two voices, two places.
- Game plan in its own persistent area.
- Evaluation bar on the side, with a hide option.
- Mate badge above the board per section 7, with its own switch.
- Board orientation follows the user's color, their pieces at the bottom.
- Controls: color, strength, style, theme, mate badge, take back, new game, export
  PGN.
- Color is chosen on the new-game screen and does not change mid-game.

### Themes

A theme is only CSS: one file per option defining light square, dark square,
highlight, and piece set. v1 ships wood, classic green, blue, marble, and high
contrast. The choice lives in `localStorage`. Adding a theme means adding a file.

## 9. Error handling

| Failure | Behavior |
|---|---|
| Stockfish not found | Clear message at startup with the install command. The app does not start. |
| Stockfish crashes mid-game | Restart the process and retry the analysis once. If it persists, warn and pause. |
| API unavailable | Play continues. Text is assembled from tags and numbers, without the model. The game never stops for lack of narration. |
| Illegal move received | HTTP 400, the piece returns to its origin. |
| Game over | Detected by python-chess: checkmate, stalemate, repetition, fifty-move rule, insufficient material. |

Degraded mode without the API is a requirement, not a courtesy: it is what makes the
app work offline.

## 10. Tests

- `persona.py`: given a fixed candidate set, verify the heuristics pick the expected
  move. No network.
- `tutor.py`: known positions with a planted blunder, verify the classification.
- `game.py`: legal and illegal move sequences, every terminal condition.
- `engine.py`: integration test verifying Stockfish responds and MultiPV arrives
  complete.
- Color: a game started with the user as black produces a GOAT move before any
  interaction, and no tutor analysis on that move.
- Perspective: the same position seen by a white user and a black user produces
  opposite signs, both correct from the mover's point of view.
- Mate: positions with known forced mate in 2, 3, and 5, verifying the distance is
  read correctly in both directions and that the badge does not leak the move.
- Short mate under low strength: verify the GOAT executes mate in up to 3 even at the
  minimum setting.
- Full flow: a short scripted game from first move to checkmate.

## 11. Out of scope for v1

- A free-text field for instructing the GOAT in natural language. Depends on the
  filter weights being stable and calibrated. Deferred to v2.
- Maia (a neural network producing human-looking moves) as an alternative to the
  filtered engine. The `engine.py` interface already allows swapping it in later.
- Opening book, saved game library, progress statistics.
- Analysis of external games imported by PGN.
- Packaged application. v1 starts from the command line.

## 12. Build order

1. `engine.py` + `game.py` — playable in the terminal against raw Stockfish.
2. `persona.py` — the GOAT gains style, still without prose.
3. `server.py` + board — playable in the browser.
4. `tutor.py` — post-move analysis with numbers.
5. `coach.py` — the two voices.
6. Themes and controls.

Each stage produces something usable. If the build stops at any point, what exists
works.
