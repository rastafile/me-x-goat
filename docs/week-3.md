# Week 3 — implementation plan

Goal: the tutor. Every user move gets classified by how much evaluation it gave
up, both sides' mistakes are counted, and the game ends with a summary of where
it was decided. Still no prose — `tutor.py` produces numbers and a move to point
at; turning that into sentences is `coach.py`, which is week 4 ("narration
layer, mate badge, tests, v1" per README).

One new module (`tutor.py`) plus changes to `server.py` and `web/`. `engine.py`,
`game.py`, and `persona.py` don't change. Read `docs/design.md` §6 (rewritten
already, see the "Asymmetric commentary" / "Mistake count" / open-question
subsections) and `docs/decisions.md` ADR 4 before starting.

---

## 0. Setup

No new dependencies. Add `tests/test_tutor.py` to the layout.

---

## 1. `tutor.py` — classification, pure function

Same discipline as `persona.py`: no Stockfish, no network, no state. Per
CLAUDE.md's testing rule, no test here may touch the network, the API, or
Stockfish — hand-built `Analysis`/`Candidate` pairs only.

### Contract

```python
@dataclass(frozen=True)
class Assessment:
    classification: str    # "excellent" | "good" | "inaccuracy" | "mistake" | "blunder"
    loss_cp: int            # >= 0, from the mover's point of view
    best_move: str | None   # UCI of the stronger alternative; None for excellent/good
    continuation: list[str] # 3-4 plies from the best line; [] for excellent/good
    offer_take_back: bool   # True only for "blunder"

def loss_cp(before: Analysis, after: Analysis, mover_color: str) -> int: ...
def classify(loss_cp: int) -> str: ...
def assess(before: Analysis, move: str, after: Analysis, mover_color: str) -> Assessment: ...
```

`before` is an `Analysis` of the position *before* the move (the mover's own
candidates). `after` is an `Analysis` of the position *after* the move —
i.e. the opponent's candidates, since it's now their turn. Neither
`persona.Choice` nor any tag ever appears in this signature (ADR 4): `assess`
doesn't know or care whether `move` came from the user or the GOAT.

### How `loss_cp` actually works

This is the same family of bug as engine.py's perspective normalization, and
gets the same care. Evaluating "how good was this move" from two single-sided
analyses, not by looking the move up in a candidate list:

1. `before.candidates[0]` is the best the mover could have played. Convert its
   `score_cp` to the mover's own perspective (flip if the mover is Black) --
   call this `best_available`.
2. `after.candidates[0]` is the opponent's best reply to whatever was actually
   played. Convert *that* to the opponent's perspective, then negate it --
   the position's value for the mover is the negative of its value for
   whoever moves next. Call this `actual_result`.
3. `loss_cp = best_available - actual_result`, clamped to `>= 0` (search noise
   or a mate-adjacent line can otherwise make this slightly negative).

This needs the *opponent's* analysis of the resulting position, not the
mover's own -- there is no shortcut through `Analysis.loss_cp` (that compares
candidates *within one side's own analysis*; this compares two analyses on
either side of a move). If `before` or `after`'s top candidate is mate-typed,
treat it the same way `persona._within_margin` avoids doing --- do not fall
back to a huge sentinel value here either; a mate-adjacent move is already
guaranteed `classify()` as a blunder or better by its sheer cp swing in
practice, but this needs a concrete test rather than an assumption.

### Classification thresholds

Starting point, to be calibrated (same spirit as `persona.py`'s margin table
and `avoid_chaos`'s spread threshold):

| Classification | Loss (cp)   |
|---|---|
| excellent | 0-10 |
| good | 11-50 |
| inaccuracy | 51-100 |
| mistake | 101-300 |
| blunder | 301+ |

### Asymmetric commentary, at the data level

design.md's asymmetric-commentary rule ("good moves get one line, or
silence") is a `coach.py` concern (week 4) -- but `assess` sets it up: `best_move`
and `continuation` are populated only for `inaccuracy`/`mistake`/`blunder`.
For `excellent`/`good`, they come back `None`/`[]`, same as `persona.choose`
returns empty tags when no heuristic fires. `coach.py` will have nothing to
elaborate on for a good move, by construction, not by a prompt instruction to
"keep it brief."

`continuation` is `before.candidates[0].pv`, sliced to 3-4 entries -- reusing
`engine.py`'s own PV data instead of asking the engine anything new.

`offer_take_back` is `classification == "blunder"`. Per design.md, always
surfaced after the explanation forms (a `coach.py`/`web` ordering concern, not
`tutor.py`'s), not before.

### Tests

All with hand-built `Analysis` pairs, no Stockfish:

- A candidate matching the best available move: `loss_cp == 0`, `"excellent"`.
- A candidate exactly at each threshold boundary: classified on the correct
  side of the line.
- `best_move`/`continuation` are `None`/`[]` for excellent and good, populated
  for inaccuracy/mistake/blunder.
- `offer_take_back` is `True` only for blunder.
- Perspective: the same pair of analyses, computed for a White mover and
  (mirrored) for a Black mover, produce the same `loss_cp` and classification
  -- the recurring perspective bug, caught the same way engine.py's and
  persona.py's own tests catch it.
- A mate-typed `before` or `after` top candidate doesn't crash `loss_cp` and
  produces a sane (not astronomically huge) result.

---

## 2. Wire `assess` into `POST /move`

This is its own session on purpose, same reasoning as week-2 session 2's
perspective-flip session: the mechanism above only works if `server.py` calls
`engine.analyse` on the *right* position at the *right* time, and this is
easy to get backwards.

### What changes in `/move`

Today: push the user's move, then (if not over) analyse once, to pick the
GOAT's reply. That single analysis is already the `after` half of the user's
assessment -- it doesn't need to be computed twice.

New: analyse the position *before* pushing the user's move too. Order
becomes:

1. `before = engine.analyse(game.fen, ...)` -- while it's still the user's turn.
2. `game.push(user_move)`.
3. If not over: `after = engine.analyse(game.fen, ...)` (existing call, now
   also captured as `after`), then `persona.choose` on `after.candidates` for
   the GOAT's reply, as today.
4. `user_assessment = tutor.assess(before, user_move, after, game.user_color)`.
   If the game *did* end on the user's own move, there is no `after` --
   `assess` isn't callable; report the classification some other way (see
   Care point below) or skip it -- decide during implementation, not here.

`GameStateResponse` gains a `tutor` field carrying `Assessment`'s contents (or
`null` on the rare no-`after` case above).

### Care point: doubling the engine cost

This is one extra `analyse` call every round that wasn't there before --
noted, not hidden. Movetime is already bounded by the strength table, so the
worst case is roughly double the wait per move, not a new order of magnitude.

### Tests

Integration-marked (needs Stockfish, same as the rest of `test_server.py`):

- A clearly bad user move gets `classification` other than `excellent`, with
  a populated `best_move`.
- A clearly good user move gets `"excellent"`/`"good"` with `best_move: null`.
- A user move that itself ends the game (checkmate/stalemate) doesn't crash
  `/move` even without an `after` analysis.

---

## 3. Mistake counts, both sides

design.md: "Every game tracks mistakes per side... reports both sides'
counts." `tutor.assess` doesn't care whose move it classifies (§1, ADR 4) --
counting the GOAT's own moves the same way costs one more `analyse` call per
round (the GOAT's own "after": analyse the position once more, following its
reply), not a design change.

### Contract

```python
# app.state.mistake_counts: dict[str, dict[str, int]]
# {"white": {"inaccuracy": 0, "mistake": 0, "blunder": 0}, "black": {...}}
```

Reset on `/new-game`. Incremented on every `assess()` call (both the user's
move and the GOAT's, each attributed to whichever color actually moved) whose
classification is `inaccuracy`, `mistake`, or `blunder` -- `excellent`/`good`
don't count as mistakes, the name says so.

`GameStateResponse` gains `mistake_counts`, always present, visible during
play per design.md ("The running count is visible during play").

### Tests

- A move classified as a mistake increments the right color's right counter.
- An excellent/good move increments nothing.
- Counts reset to zero on `/new-game`.

---

## 4. End-of-game summary

design.md: the mistake count "is the centerpiece of the end-of-game summary,
which reports both counts and identifies where the game was decided."

### Contract

```python
# app.state tracks the single worst Assessment seen this game (by loss_cp),
# alongside which color and which ply produced it.

# GameStateResponse, only populated when is_over:
# "summary": {"mistake_counts": {...}, "decided_at_ply": int, "decided_by": "white"|"black", "loss_cp": int} | null
```

"Where the game was decided" is the single largest `loss_cp` seen across the
whole game, from either side -- not necessarily the *last* move, and not
necessarily the user's.

### Tests

- A short scripted game with a known, deliberate blunder partway through: the
  summary names the correct ply and color.
- A game with no move above "good": summary still present, `loss_cp` reflects
  whatever the actual largest (small) loss was -- there is always a
  worst move, even in a clean game.

---

## 5. `web/`: tutor panel, mistake counters, take-back offer

Per design.md §8, the tutor panel is visually distinct from the GOAT's own
panel -- two voices, two places (the GOAT's status line already exists from
week 2; this adds a second one). No prose yet, same reason as everywhere else
this week: numbers and a classification word, not sentences.

### Contract

- A tutor status area, separate from the existing GOAT status line, showing
  the last classification and (when populated) `best_move`/`continuation` as
  plain UCI/SAN for now -- not narrated text.
- Running mistake counters for both sides, visible throughout play.
- On `blunder`, a take-back prompt (a button, reusing the existing
  `/take-back` endpoint -- no new endpoint needed) appears after the rest of
  the analysis is shown, per design.md's ordering rule.
- End-of-game summary rendered when `is_over`.

### Tests

Manual, same as weeks 2's board sessions: play a full game, confirm the
tutor panel updates only on the user's moves, confirm a deliberately bad move
shows a take-back offer, confirm the summary appears at game end and names a
plausible turning point.

---

## 6. Work order

| Session | Build | Done when |
|---|---|---|
| 1 | `tutor.py`: `Assessment`, `loss_cp`, `classify`, `assess` | hand-built before/after pairs classify correctly, both colors |
| 2 | Wire `assess` into `POST /move` (the new "before" analysis) | a live game's `/move` response includes a correct `tutor` field |
| 3 | Mistake counts, both sides, reset on `/new-game` | counts increment correctly, visible in the API response |
| 4 | End-of-game summary | summary names the right ply/color in a scripted blunder test |
| 5 | `web/`: tutor panel, counters, take-back offer, summary display | a full game shows tutor feedback throughout and a summary at the end |
| 6 | Full suite green; one full game per color played manually, confirming tutor output at each step | suite green; both games show sane tutor output start to finish |

---

## 7. Definition of done

A full game played in the browser, one as White and one as Black, where every
user move is classified and a stronger alternative is shown for anything
below "good", a deliberate blunder produces a take-back offer, both sides'
mistake counts stay correct throughout, and the game ends with a summary
naming where it was actually decided. Test suite green, including
`pytest -m "not integration"`.

---

## 8. Not this week

- Any prose. `tutor.py` returns a classification word, a UCI move, and
  numbers -- turning that into "you gave up a full rook here" is `coach.py`,
  week 4.
- The mate badge (design.md §7). Needs its own on/off switch and its own
  "never reveal the move" care; a distraction from the tutor itself.
- Answering the open question left in design.md §6: how many mistakes a
  player can absorb before feedback should throttle to "only the worst two or
  three." Still pending a chess teacher's input; this week's tutor comments
  on every qualifying move, unthrottled.
- Recalibrating the classification thresholds or the margin/chaos-spread
  numbers from earlier weeks. Guess now, as always; measure later.
