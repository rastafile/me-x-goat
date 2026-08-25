# Week 2 — implementation plan

Goal: the same game, playable in a real browser instead of the terminal. HTTP
server, draggable board, themes. No tutor, no narration, no mate badge — those
are week 3 and week 4.

Two new pieces: `server.py` (FastAPI) and `web/` (HTML/JS/CSS, `cm-chessboard`).
`engine.py`, `game.py`, and `persona.py` don't change in spirit — `game.py` gets one
small addition (see session 3). Read `docs/design.md` sections 3, 4, and 8 before
starting; this plan adapts them to not need `tutor.py`/`coach.py`, which don't exist
yet.

---

## 0. Setup

```bash
pip install fastapi "uvicorn[standard]"
pip freeze > requirements.txt
```

`cm-chessboard` (MIT) replaces chessground (GPL-3) — see `docs/design.md` §3 for
why chessground doesn't work here the way Stockfish's subprocess isolation does.
Vendor it directly into `web/vendor/`, from the npm package's `dist/` output, rather
than loading it from a CDN: the app runs fully offline, and unlike Stockfish there's
no license reason to keep it external.

Layout addition:

```
me-x-goat/
  src/
    server.py
  web/
    index.html
    app.js
    styles/
      base.css
      wood.css
      classic-green.css
      blue.css
      marble.css
      high-contrast.css
    vendor/
      cm-chessboard/         # MIT, vendored, not fetched at runtime
  tests/
    test_server.py
```

---

## 1. `server.py` — game endpoints

The server holds exactly **one** game in memory, in `app.state`, created and reset
through the endpoints below — this is a local, single-user app, not a multi-tenant
service. No sessions, no auth, no game IDs.

### Contract

```python
# app.state.engine: Engine        -- one process, created at startup, closed at shutdown
# app.state.game:   Game | None   -- None until the first /new-game call
# app.state.style:  str
# app.state.strength: int

# POST /new-game
# body:  {"color": "white"|"black"|"random", "strength": int = 1400, "style": str = "carlsen"}
# 200:   {"fen": str, "user_color": "white"|"black", "legal_moves": [str],
#          "goat_move": {"uci": str, "san": str, "tags": [str]} | null,
#          "evaluation": int | null, "is_over": bool, "outcome": str | null}

# POST /move
# body:  {"uci": str}
# 200:   same shape as /new-game's response, minus user_color (it doesn't change)
# 400:   {"detail": str}                              -- illegal move; state untouched
# 422:                                                  -- malformed body (FastAPI's own validation)

# POST /take-back
# 200:   same shape as /move's response

# GET /pgn
# 200:   text/plain PGN

# GET /                                                 -- serves web/index.html
# GET /static/*                                         -- serves web/ (StaticFiles)
```

`legal_moves` is the flat UCI list from `Game.legal_moves()`. The frontend groups it
by origin square itself — nothing server-side reshapes it.

`goat_move` is `null` only in `/new-game`'s response when the user is White (no
opening move to report). It's also `null` on any response where `is_over` is true —
no reply to make.

`evaluation` is the position's top-candidate score, flipped to the user's
perspective (session 2). `null` when the position is terminal, or when the top
candidate is mate-typed (mate display is week 4's badge, not this number).

### Engine lifecycle

One `Engine`, created once via FastAPI's `lifespan` context manager and closed on
shutdown — never per-request. If `Engine()` raises `EngineUnavailable` at startup,
the server does not start: print the install command and exit, per design.md §9's
error table. `@app.on_event("startup")` is deprecated; use `lifespan`.

### Analysis time

`persona.choose` needs candidates; candidates need a `movetime_ms`. Reuse the
"Analysis time" column already in `docs/week-1.md`'s margin table — `server.py` is
where an orchestration decision like this belongs, not `engine.py` or `persona.py`,
which stay pure/stateless.

```python
_ANALYSIS_TIME_TABLE = [
    (800, 50), (1200, 100), (1600, 200), (2000, 400), (2400, 800),
]  # same shape and interpolation as persona._margin_cp's table
```

### Tests

All of these need a real Stockfish the same way `engine.py`'s integration tests do
(the app can't even start without one) — mark the whole file `integration`.

- `POST /new-game` with `color=white`: `goat_move` is `null`.
- `POST /new-game` with `color=black`: `goat_move` is already populated — the
  opening move happened inside this same call.
- `POST /new-game` with `color=random`: `user_color` in the response is resolved,
  never `"random"`.
- `POST /move` with a legal move: response includes the GOAT's reply and the
  updated FEN reflects both plies.
- `POST /move` with an illegal move: 400, and the FEN is unchanged (confirmed by a
  follow-up legal `/move` with the *original* move succeeding).
- `POST /move` that delivers checkmate: `is_over` true, `goat_move` null.

---

## 2. Evaluation perspective at the output boundary

Its own session on purpose. CLAUDE.md and design.md both single this out as the
project's most common source of bugs, and nothing has touched it yet since
`engine.py` normalizes to White and stops. `server.py` is "the server's output
boundary" — design.md's one and only place the flip happens.

### Contract

```python
def _evaluation_for_user(candidate: Candidate, user_color: str) -> int | None:
    # candidate.score_cp is White-perspective; None on a mate-typed candidate.
    ...
```

Only `/new-game` and `/move` responses go through this. `game.py`, `engine.py`, and
`persona.py` never see or produce a user-perspective number.

### Tests

- The same position, requested as `user_color="white"` and as `user_color="black"`:
  `evaluation` has opposite sign in the two responses, and in both cases a positive
  number means the *user* is doing well — not "White is doing well".
- A mate-typed top candidate: `evaluation` is `null` — not a crash, not a fabricated
  huge number standing in for mate.

---

## 3. `Game.ply_count`, `POST /take-back`, `GET /pgn`

### `game.py` addition

Take-back needs to know how many plies to pop, and `Game` doesn't expose that today.
Add one property:

```python
@property
def ply_count(self) -> int: ...   # number of half-moves played so far
```

Don't derive this from the FEN's halfmove/fullmove fields — the halfmove clock
resets on captures and pawn moves, and neither field is "plies played from this
game's start" once `pop()` has been used.

### Take-back

Pops back to the user's turn. Almost always two plies — the user's move, then the
GOAT's reply — except right after a Black game's opening, where only the GOAT's
single opening move is on the stack yet. `docs/week-1.md`'s `game.py` section
already flagged this asymmetry without resolving it; this is where it's actually
handled, by checking `ply_count` before popping rather than hardcoding "pop twice".

### PGN export

`GET /pgn` returns `game.pgn()` as-is. No new logic.

### Tests

- `ply_count` after N pushes is N; after a push+pop it's back to N-1.
- Take-back after a normal round (White user, then Black user) returns to the exact
  position before the user's last move.
- Take-back immediately after a Black game's opening (no user move yet) returns to
  the starting position instead of raising from popping an empty stack.
- `GET /pgn` after a few moves matches `game.pgn()`.

---

## 4. `web/` — board and wiring

Static HTML/JS/CSS, no build step, no framework — same "no more machinery than the
task needs" bias as the rest of the project. `cm-chessboard` loads as a vendored ES
module.

### Contract

- `index.html`: board, new-game panel, take-back / export-PGN buttons, theme
  picker. No tutor panel, no GOAT commentary panel, no mate badge, no evaluation
  bar — those need modules this week doesn't build (see "Not this week").
- `app.js`: calls `/new-game` and `/move`, feeds the response's `legal_moves` into
  `cm-chessboard`'s `validateMoveInput` hook to reject illegal drops before they're
  attempted. `cm-chessboard` has no chessground-style pre-computed destination map;
  the same legal-move list still drives the restriction, just through a callback
  instead of disabled squares.
- Board orientation follows `user_color` (`cm-chessboard`'s `orientation` option).
- Promotion: unlike the CLI, the browser can actually ask which piece. On a
  promotion-eligible drop, show a four-piece picker (Q/R/B/N) before sending the
  UCI move — design.md's care point ("the interface must ask which piece") applies
  here; "assume queen" was the CLI's shortcut, not the rule.

### Tests

Manual — browser interaction isn't unit-testable the way Python is: one full game
played in a real browser per color, confirming orientation, legal-move restriction,
the promotion picker, and the take-back/PGN buttons all work against the real
server.

---

## 5. New-game controls

Color, strength, and style pickers on a start screen; "new game" resets state via
`/new-game`. Style options are `carlsen` and `raw` — the two `persona.py` actually
implements. No Tal/Petrosian in the picker: CLAUDE.md is explicit that styles beyond
Carlsen aren't in scope, and `raw` isn't a new style, it's the already-implemented
empty-heuristics case.

### Tests

Manual: changing strength/style before starting visibly changes GOAT behavior
across a game — the browser-level version of `persona.py`'s own "different styles
produce different choices" test.

---

## 6. Themes

One CSS file per theme, each defining light square, dark square, highlight, and
piece set, per design.md §8. Ship wood, classic green, blue, marble, and high
contrast. Selection persists in `localStorage`. Adding a theme means adding a file
and a picker entry — no JS branches on which theme is active.

### Tests

Manual: switching themes changes board appearance without a reload; the choice
survives a page refresh.

---

## 7. Work order

| Session | Build | Done when |
|---|---|---|
| 1 | `server.py`: `/new-game`, `/move`, engine lifecycle, analysis-time table | a game played end to end via FastAPI's `TestClient`, no browser |
| 2 | Evaluation perspective at the output boundary | same position, both colors, opposite signs |
| 3 | `Game.ply_count` + `/take-back` + `/pgn` | take-back right after a Black-opening game doesn't crash |
| 4 | `web/`: board, legal-move restriction, orientation, promotion picker | a full game playable by dragging pieces in a real browser |
| 5 | New-game controls (color/strength/style) | changing strength/style before starting changes GOAT behavior |
| 6 | Themes | five themes switchable, persisted across reload |
| 7 | Server test suite green; one full game per color played manually through the browser | suite green; both games reach a result |

---

## 8. Definition of done

A full game played in a real browser, one as White and one as Black, from first move
to result, dragging pieces restricted to legal destinations, board oriented to the
user's color, all five listed themes switchable, take-back and PGN export both
working. Server test suite green — including `pytest -m "not integration"` staying
green for anyone without Stockfish installed, even though the server itself won't
start without it.

---

## 9. Not this week

- `tutor.py`, `coach.py` — no post-move analysis, no narration in either voice.
  Week 3/4.
- Mate badge (design.md §7) — needs the tutor's evaluation machinery to be worth
  building well; the plain `evaluation` number added this week is not the badge.
- Evaluation bar UI — the number now exists in the API response, but nothing
  renders it yet; that's a tutor-adjacent display decision, not board-wiring.
- Persistent "game plan" panel — depends on `persona.py` flagging structural
  transitions, which it doesn't do yet.
- Styles beyond Carlsen/raw, weight calibration — still explicitly out of scope
  per CLAUDE.md.
- Concurrency / multi-game support — one game in memory is the whole point of
  "local, single-user".
