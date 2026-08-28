# Week 6 — implementation plan

Goal: two things `CLAUDE.md` and `docs/design.md` have deferred since week 1,
deliberately unlocked this week (see `CLAUDE.md`'s Scope section and invariant
1, both amended for this):

- **Track A** — replace `persona.py`'s guessed style weights and margin table
  with values informed by actual self-play data, instead of the week-1 guess
  that was never revisited.
- **Track B** — a curated opening book, the "actual fix" ADR 5 identified for
  style depth and explicitly deferred. `CLAUDE.md`'s invariant 1 now reads
  "Stockfish's analysis **or a curated, deterministic opening book**" for
  exactly this reason — a book move is still data plus a deterministic rule,
  never the language model, and must always be legal in the current position.

The two tracks don't depend on each other and are ordered so Track A can start
immediately; Track B's first session needs a PGN file (or files) from the user
before implementation begins.

Read `docs/decisions.md` ADR 5 before starting Track B — it already frames why
an opening book is the real lever for style, not a nice-to-have.

---

## Track A — data-driven weight calibration

### 0. Self-play harness

A standalone script, not part of `src/` or `pytest` — it deliberately touches
Stockfish and plays full games, which is exactly what `CLAUDE.md`'s testing
rule keeps out of `persona.py`'s own unit tests.

#### Contract

- New `tools/self_play.py`. Imports `engine.py`/`persona.py`/`game.py`
  directly (no HTTP, no server). CLI args: style, strength (or a list of
  strengths), number of games, a ply cap (games that run long are cut off and
  recorded as unresolved, not left to run indefinitely).
- Each game: GOAT plays both sides at the given style/strength (no user, no
  tutor — this is about `persona.py`'s own move choice, not the tutor).
  Records, per ply: which tag(s) fired (if any), the winning heuristic's
  total score, and whether any heuristic fired at all (a plain tie-break vs.
  an actual style preference are different outcomes worth telling apart).
- Output: a summary per run — tag firing frequency, how often no heuristic
  fired at all, average game length, how often `avoid_chaos`'s penalty
  actually changed the winning candidate vs. just adjusted a score that
  wasn't going to win anyway.
- Keep movetime low (reuse `server.py`'s `_movetime_ms` or similar) — this is
  about move *choice* patterns, not engine strength, so games don't need to
  be slow to be informative.

#### Tests

None (it's a tool, not app code) — but a smoke run (a handful of games at one
strength) confirms it runs to completion and produces a readable report
before session 1 uses it for real.

---

### 1. Run the harness, review the data

#### Contract

- Run `tools/self_play.py` across the `_MARGIN_TABLE`'s existing strength
  anchors (800/1200/1600/2000/2400), plus 2800, at least a few dozen games
  per strength — enough for tag-frequency numbers to mean something, not so
  many that a session takes forever.
- Review the report together with the design intent each heuristic states in
  `design.md` §5's table (e.g., does `queen_trade` actually fire near as
  often as "high weight" implies? does `avoid_chaos` ever change a decision,
  or is its weight too small next to the others to matter?).
- No code changes this session — it's entirely about producing and reading
  the data Track A session 2 acts on.

#### Tests

None — this session's output is a report, not code.

---

### 2. Adjust weights, document, update tests

#### Contract

- Adjust `WEIGHTS` (and `_MARGIN_TABLE`/`_CHAOS_SPREAD_CP` if the data
  supports it) in `persona.py`, based on session 1's findings — not a
  re-guess, a change traceable to a specific observation in the report.
- New ADR in `docs/decisions.md` (next number after ADR 9) recording: the
  harness methodology, the before/after weight table, and the reasoning tying
  each change to what the data showed. This is exactly the "would look
  arbitrary from the code alone" case ADR 8/9 already set the pattern for.
- `tests/test_persona.py` has one hardcoded `reason_score` assertion
  (currently `5.5`, from `queen_trade` + `toward_endgame`'s old weights) —
  update it to match the new numbers, and add a comment noting it's pinned to
  the current `WEIGHTS` table on purpose (so the next recalibration knows to
  touch it).
- Re-run the full suite; nothing about `persona.py`'s public shape changes,
  only its constants, so no other test should need touching.

#### Tests

`pytest` full suite green. Manual: play a few real games at a couple of
strengths through `web/`, confirm nothing about the GOAT's behavior looks
broken (a sanity check, not a substitute for the harness's own data).

---

## Track B — opening book

### 3. Book format and ingestion (needs the user's PGN)

Blocked on the user supplying one or more PGN files. Nothing here starts
before that arrives.

#### Open design questions this session must resolve with the user, not decide alone

- **Matching strategy**: exact move-sequence prefix match (the game so far
  must match a book line move-for-move) is the v1 scope — no transposition
  detection (recognizing the same position reached by a different move
  order). Confirm this is an acceptable v1 limitation before building.
- **Precedence**: a forced mate (`design.md` §7, `_SHORT_MATE_MAX`) must
  still outrank a book move if one is somehow available this early — book
  lookup sits after the forced-mate check and before the heuristic filter in
  `persona.choose`. While in book, does the move-time heuristic filter run at
  all, or does the book move bypass it entirely? Proposed: bypass entirely —
  ADR 5 frames the book as the actual mechanism for style, superseding the
  move-time filter's approximation of it, not stacking with it.
  Confirm with the user before implementing.
- **Strength interaction**: should low strength make the GOAT "forget" the
  book sooner (leave book depth earlier), consistent with an inattentive
  persona, or does book depth stay fixed regardless of strength (relying on
  curated lines being short enough that this rarely matters)? No answer
  assumed here — resolve with the user this session.

#### Contract

- Parse the supplied PGN(s) into move sequences (UCI), one list per game/
  line. A short design note (or the ADR below) on how multiple PGNs that
  share an opening but diverge later are represented — a simple prefix tree
  keyed by move sequence is the likely shape, one tree per style.
- New ADR in `docs/decisions.md`: records the matching-strategy and
  precedence decisions above, and that this supersedes ADR 5's "Rejected for
  now" section specifically (ADR 5 stays, as the historical record of why it
  was deferred — this new ADR is what un-defers it).

#### Tests

None yet — this session is ingestion + design, not runtime integration.

---

### 4. `opening_book.py` and `persona.py` integration

#### Contract

- New pure module `opening_book.py` (same shape as `persona.py`/`tutor.py`:
  no network, no Stockfish, no state). Input: the move history so far (UCI)
  and a style name; output: the next book move, or `None` if out of book or
  the style has no book data.
- `persona.choose` gains the move history as a parameter, consults
  `opening_book.py` after the forced-mate check and before the heuristic
  loop (per session 3's precedence decision), and returns early with a
  `Choice` tagged `opening_book` when the book has an answer.
- `server.py` passes the move history through (it already tracks the game
  via `game.py`; this is threading an existing value, not new state).
- A book move must always be a legal move in the current position — assert
  this rather than trusting the source data blindly (a malformed or
  transposed PGN entry should fail loudly in testing, not play an illegal
  move in production).

#### Tests

Hand-built book data (a tiny fixture tree, 2-3 lines deep) — no PGN parsing,
no Stockfish, matching `CLAUDE.md`'s rule that `persona.py`'s tests never
touch either. Cover: a move in book, a move that leaves book (falls through
to the heuristic filter), an empty book for a style (falls through
immediately), and the illegal-book-move assertion actually firing on a
deliberately bad fixture.

---

### 5. Cross-checks and close-out

#### Contract

- Confirm the mate-in-3 rule (`design.md` §7) still wins over a book move in
  a hand-built position where both are technically available (should never
  happen with real book data this early in a game, but the precedence order
  must hold regardless).
- Confirm `narration.py`/`coach.py` produce sensible text for the new
  `opening_book` tag — it's a legitimate new tag alongside the five Carlsen
  heuristics and needs at least a fallback phrase in `narration.py`'s
  deterministic path (`coach.py`'s API path can describe it more naturally,
  but the offline fallback must not be empty or wrong for this tag).
- Update `design.md` §5 to describe the book (no longer "out of scope for
  v1"), and `docs/decisions.md`'s note under ADR 5 pointing to the new ADR
  that supersedes its "Rejected for now" section.
- Full suite green.

#### Tests

`pytest` full suite. Manual: a real game through `web/` where the first
several moves come from the book (visible via the `opening_book` tag's
commentary), then transitions naturally into heuristic-filtered play once
out of book.

---

## 6. Work order

| Session | Track | Build | Done when |
|---|---|---|---|
| 0 | A | Self-play harness | runs to completion, produces a readable tag-frequency report |
| 1 | A | Run harness, review data | report reviewed against `design.md` §5's stated intent per heuristic |
| 2 | A | Adjust weights, ADR, tests | weights changed with a documented reason per change, suite green |
| 3 | B | Book format + ingestion (needs user's PGN) | design questions resolved with the user, ADR written |
| 4 | B | `opening_book.py` + integration | book moves play through `persona.choose`, hand-built tests pass |
| 5 | B | Cross-checks, close-out | mate precedence holds, narration covers the new tag, docs updated, suite green |

---

## 7. Definition of done

`persona.py`'s weights and margins are traceable to observed self-play data,
not a week-1 guess. A curated opening book gives the GOAT's opening play real
character, consulted before the move-time heuristic filter and always
subordinate to the mate-in-3 rule. Both changes recorded as ADRs. Full suite
green throughout.

---

## 8. Not this week

- Transposition-aware book lookup (recognizing the same position via a
  different move order) — the v1 book is a straight move-sequence match.
- Automatically expanding the book from arbitrary PGN sources at runtime —
  ingestion is a one-time, offline step producing a local data file, same
  vendoring principle as fonts and `cm-chessboard`.
- Any change to `tutor.py` or the mistake-count threshold (`design.md` §6's
  own open question) — untouched this week.
- Styles beyond Carlsen, Maia, packaging, performance work — still blocked
  per `CLAUDE.md`'s Scope section; this week's unlock is specific to weight
  calibration and the opening book only.
