# Week 7 — implementation plan

Goal: an optional chess clock. Confirmed with the user before this plan was
written:

- **Time control**: presets, not free-form minutes/increment input --
  matches the settings panel's existing convention of a small, fixed set of
  choices (color, style, theme). Off by default, same as today's untimed
  play -- "originally we can play without time" (the user's own framing).
  Presets for v1: **No clock** (default), **Bullet** (1+0), **Blitz**
  (3+2), **Rapid** (10+5), **Classical** (30+0) -- minutes+increment
  seconds, standard values matching common convention elsewhere.
- **Both sides have a clock**, not just the user's -- the user's own
  request named "each player's remaining time." The GOAT's own analysis
  time stays exactly what it is today (`_movetime_ms`, 50-800ms by
  strength) -- its clock is real bookkeeping (the same wall-clock
  mechanism ticks for both sides), but nothing adapts its thinking time to
  its own remaining budget. At today's analysis times it will essentially
  never run low regardless of time control; adaptive time management is
  real added scope with no clear benefit yet.
- **Timeout, insufficient material**: the side whose time expires loses --
  *unless* the opponent has insufficient material to deliver mate (FIDE's
  own rule), in which case it's a draw. `python-chess`'s
  `Board.has_insufficient_material(color)` already answers this; no need
  to approximate it.
- **Take-back does not refund time.** The clock only ever moves forward;
  popping a move in `game.py` has no effect on it.

Not part of this plan, confirmed as unrelated to a v1 clock: pausing,
adaptive GOAT time management, and any change to `persona.py`'s own move
choice (the clock is orchestration state, same category as mistake counts
and assessment history -- it never influences which move gets played).

---

## 0. `src/clock.py` and server-side plumbing

### Contract

- New module `src/clock.py`. A small stateful class (not a pure function --
  wall-clock time is an inherent side effect, same category as
  `engine.py`'s subprocess I/O), but every method that reads "now" takes
  it as an explicit `now_ms` parameter rather than calling `time.time()`
  internally, so it stays deterministically testable without mocking the
  clock:
  - `Clock(white_ms: int, black_ms: int, increment_ms: int)`
  - `start_turn(color: str, now_ms: int) -> None`
  - `stop_turn(now_ms: int) -> None` -- deducts elapsed time from the
    color whose turn was running, then applies the increment.
  - `remaining_ms(color: str) -> int`
  - `is_flagged(color: str, now_ms: int) -> bool` -- true if that color's
    clock, including whatever elapsed since its turn started (if it's
    currently running), has hit zero.
- `server.py`: `app.state` gains an optional `Clock | None` (`None` means
  no time control this game -- today's behavior, completely unaffected).
  `NewGameRequest` gains an optional `clock` field (one of the five preset
  names above). `/new-game` constructs the `Clock` accordingly and starts
  the mover's turn.
  Every `/move` handler: stops the mover's clock (deducts elapsed, applies
  increment) before validating the move itself, then -- if the game isn't
  over -- starts the new mover's clock (this naturally covers the GOAT's
  own "thinking time" too, since its reply is computed synchronously in
  the same request, before the user's clock starts again).
- `GameStateResponse` gains `white_time_ms: int | None` and
  `black_time_ms: int | None` (both `None` when no clock this game) so
  `web/` can render and locally tick a countdown between server responses.

### Tests

`src/clock.py` tested directly with injected `now_ms` sequences -- no
`time.time()`, no server, no network. Cover: increment applied only to the
side that just moved, `remaining_ms` never goes negative in the returned
state (flagging is a separate query, not an exception), a currently-running
turn's elapsed time is included in `is_flagged` even before `stop_turn` is
called for it.

---

## 1. Timeout as a real game-over outcome

### Contract

- New endpoint `POST /timeout` with `{"color": "white" | "black"}` --
  called by the client when its own local countdown display reaches zero.
  The server never trusts this claim directly: it recomputes real elapsed
  time itself via `Clock.is_flagged`. If genuinely expired, the game ends;
  if not (client-side drift fired early), this is a harmless no-op --
  returns the current, still-in-progress `GameStateResponse` unchanged.
  No 400s for a false alarm; a race here is expected, not exceptional.
- On a real timeout: `game.py`/`server.py` need a way to end the game
  with an outcome `python-chess` itself doesn't produce (`Termination`
  has no timeout value). Represent it as a new outcome string
  `"timeout"` alongside the existing checkmate/stalemate/etc. values
  wherever `Game.outcome()`'s string is consumed (`GameStateResponse`,
  `narration.py`'s `_OUTCOME_PHRASES`) -- *unless* the non-flagged side
  has insufficient mating material, in which case reuse the existing
  `"insufficient_material"` outcome and its current phrase untouched (it
  reads correctly regardless of what triggered the draw).
- `narration.py` gains a `"timeout"` phrase in both languages that names
  which color ran out -- unlike the other outcome phrases, this one needs
  a parameter (nothing else about *why* the game ended states who lost;
  checkmate/stalemate imply it from whose move ended things, timeout
  doesn't). Design the phrase and its parameter now, during
  implementation, rather than here.
- End-of-game summary (mistake counts, `design.md` §6) is unaffected --
  it already just reports both sides' recorded mistakes regardless of how
  the game ended, no special-casing needed for a timeout ending.

### Tests

Hand-built: a `Clock` already at zero for one color, confirm `/timeout`
ends the game with the right outcome in both the normal case and the
insufficient-material-draw case. A `/timeout` call for a color that
hasn't actually flagged leaves the game running. A game with no clock
(`None`) rejects or no-ops on `/timeout` cleanly -- it should never be
reachable from `web/` in that state, but the endpoint must not crash if
it somehow is.

---

## 2. `web/` clock UI

### Contract

- Settings panel gains a time-control row (matches the existing
  label-left/control-right convention): the five presets as a `<select>`,
  same shape as style/theme/language today. Selecting one takes effect on
  the *next* new game, same as every other setting.
- Two clock displays near the board -- reads through `docs/ui-reference/`
  DESIGN-SYSTEM.md's typography (monospace numerals, matching
  `.settings-value`'s existing convention) rather than inventing a new
  visual language. Exact placement (above/below the board, beside the
  eval bar) is this session's own call, guided by the reference's spirit
  per `docs/week-5.md`'s own "not pixel parity" standard.
- Client-side countdown: on every server response carrying
  `white_time_ms`/`black_time_ms`, resync a local `setInterval` display
  for whichever side's clock is now running; the other side's display
  holds still. When the running side's local display would hit zero,
  call `POST /timeout` with that color and apply whatever
  `GameStateResponse` comes back (same `applyState` path every other
  response already goes through).
- No clock UI at all renders when `white_time_ms` is `None` -- the
  no-time-control game looks exactly as it does today.

### Tests

Manual: each of the five presets playable start to finish; a deliberately
low-time preset (Bullet) run down to a real timeout, confirming the UI
reflects the server's outcome correctly in both the loss and the
insufficient-material-draw case. Confirm a no-clock game shows no clock UI
at all.

---

## 3. Take-back and the clock

### Contract

- Confirm (not "implement" -- this should already fall out of session 0's
  design for free): `POST /take-back` pops the move in `game.py` but the
  `Clock`'s deducted time for that move stays deducted. No new code
  expected here; this session is verification, and a real fix only if the
  design didn't actually hold.
- Restart the *taken-back* mover's turn on the clock (their turn is
  running again, same as after any other move that leaves the game
  in-progress) -- this part **is** real behavior, not just a check: the
  clock must resume ticking for whoever is now to move, exactly as it
  does after a normal move.

### Tests

Hand-built: play a move (clock deducts and applies increment), take it
back, confirm `remaining_ms` still reflects the deduction (not refunded)
and the correct side's turn is running again afterward.

---

## 4. Cross-checks and close-out

### Contract

- Confirm the clock UI doesn't clash with any of the five board themes,
  particularly `high-contrast` (same discipline as `docs/week-5.md`
  session 4) -- run the same kind of contrast check that session used if
  new text tokens are introduced.
- Confirm the offline narration fallback (`narration.py`, no API key)
  produces correct text for every new outcome/phrase this plan adds --
  `coach.py`'s degraded-mode guarantee (`design.md` §9) must hold for the
  clock exactly as it does for everything else.
- `CLAUDE.md`'s Architecture section gains a `clock.py` row, same table
  shape as every other module.
- `design.md` gains a section describing the clock (numbering follows
  whatever `design.md` looks like at that point -- check before writing).
  New ADR in `docs/decisions.md` if any decision here would look
  arbitrary from the code alone (the outcome-string choice, most likely).
- Full suite green.

### Tests

`pytest` full suite. Manual: one full timed game per color, default theme
and `high-contrast`, covering a real timeout in at least one of them.

---

## 5. Work order

| Session | Build | Done when |
|---|---|---|
| 0 | `clock.py` + server plumbing | clock decrements correctly across a scripted move sequence, no UI yet |
| 1 | Timeout as a game-over outcome | `/timeout` ends the game with the right outcome, including the insufficient-material draw |
| 2 | `web/` clock UI | all five presets playable, a real timeout reflected correctly in the UI |
| 3 | Take-back + clock | time spent on a taken-back move stays deducted, turn resumes correctly |
| 4 | Cross-checks, close-out | themes unaffected, offline fallback covers new text, suite green |

---

## 6. Definition of done

An optional chess clock, off by default, with five presets. Both sides
timed identically; the GOAT's own move-choice logic is completely
unaffected. Timeout ends the game correctly, including the FIDE
insufficient-material exception. Take-back never refunds time. No change
to `persona.py`'s move selection, `tutor.py`, or any existing invariant.

---

## 7. Not this week

- Pausing the clock.
- The GOAT adapting its analysis time to its own remaining budget.
- Any time-control format beyond the five fixed presets (no free-form
  minutes/increment input).
- Any change to how moves are chosen, narrated, or assessed beyond the
  new timeout outcome string itself.
