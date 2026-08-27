# Week 4 — implementation plan

Goal: the narration layer, the mate badge, the evaluation bar, the game plan
panel, one remaining error-handling gap, and v1 close-out. Everything numeric
that `tutor.py` and `persona.py` already produce turns into prose in both
supported languages; the interface gains the three pieces design.md §7/§8
describes that no week has built yet.

This is larger than week 3 — nine sessions instead of six. It maps to
README's one-line description ("narration layer, mate badge, tests, v1") but
that line covers more ground than it looks. Nothing stops us from splitting
this across more than one calendar week; the "week" label is organizational,
not a deadline. Say so if you'd rather split it after reviewing this.

Read `docs/design.md` §5 ("Game plan"), §6, §7, §8, §9 (error handling), and
`docs/decisions.md` ADR 6 before starting -- ADR 6's "Known limitation" is
this week's session 1.

---

## 0. Setup

New dependency: the Anthropic SDK (`anthropic` on PyPI) for `coach.py`.
`ANTHROPIC_API_KEY` is already documented in README's configuration table --
this is the week it actually gets read. Add `tests/test_coach.py` and
`tests/test_narration.py` (narration.py has no dedicated test file yet) to
the layout. No changes to `engine.py`, `game.py`, or `tutor.py` this week
outside of session 8's crash-resilience work.

---

## 1. Close ADR 6's known limitation: narration.py speaks both languages

`narration.py`'s phrase tables (`_LEAD_PHRASES`, `_OUTCOME_PHRASES`,
`_NO_TAG_PHRASE`) are hardcoded English today -- the exact gap CLAUDE.md's
language rule and ADR 6 both flag. This session closes it, and gives the
server a language to know about at all, before `coach.py` (sessions 2-3)
needs one.

### Contract

- `narration.py`'s phrase tables become `dict[str, dict[str, str]]`, keyed
  by language then by tag/outcome -- same two languages as `web/i18n.js`
  (`"en-US"`, `"pt-BR"`), same convention (one dict per language, no
  fallback-string English hardcoded elsewhere).
- `describe_move(analysis, choice, game, language)` gains the parameter.
  `play_cli.py`'s call site passes `os.environ.get("OUTPUT_LANGUAGE", "en-US")`
  directly (it has no page, no switch -- ADR 6's "known limitation" resolves
  exactly this way for it).
- `NewGameRequest` gains `language: str = "en-US"`. `server.py` stores it on
  `app.state.language` for the game's duration (same lifetime as `style`/
  `strength` -- set once at `/new-game`, read for every subsequent `/move`).
  Invalid/unknown values fall back to `"en-US"`, same rule `web/i18n.js`
  already applies client-side.
- `web/app.js`'s `startNewGame` sends the page's current language (already
  in `localStorage` via `i18n.js`) as this new field.

### Tests

- `narration.py`: same fixed `Analysis`/`Choice`/`Game` inputs, both
  languages, assert the expected phrase per language -- no test may touch
  the network or Stockfish (unchanged rule, still a pure function).
- `server.py`: `/new-game` with `language: "pt-BR"` accepted; an unknown
  value falls back to `"en-US"` rather than erroring.

---

## 2. `coach.py` — the GOAT's voice

### Contract

```python
def narrate_goat_move(analysis: Analysis, choice: Choice, game: Game, language: str) -> str: ...
```

Calls the Anthropic API with the same inputs `describe_move` already takes,
asks for prose in `language`, grounded in `choice.tags` and the evaluation --
never inventing a reason the move wasn't actually chosen for (persona.py's
tags are the raw material, per design.md §5). On any API failure (network,
timeout, malformed response, missing key), falls back to
`narration.describe_move(...)` immediately -- the game is never blocked on
the network (CLAUDE.md invariant 5).

Wired into `/new-game` and `/move`: `GoatMove` gains a `commentary: str`
field carrying whichever text was produced (LLM or fallback -- the client
never needs to know which).

### Tests

- Mock the Anthropic client: a successful response is returned verbatim; a
  raised exception falls back to `narration.describe_move`'s exact output.
- No test in this file may make a real network call -- same discipline as
  `tutor.py`/`persona.py`, extended to `coach.py`'s fallback path (the
  success path is mocked, never real, in the test suite).
- Integration-marked test (needs `ANTHROPIC_API_KEY`, skipped without one):
  a real call returns non-empty prose mentioning something sane.

---

## 3. `coach.py` — the tutor's voice

The tutor has no fallback-text builder anywhere yet -- the web UI's own
client-side templates (`web/i18n.js`, session 5 of week 3) are the only
place tutor text is assembled today, and they're English/Portuguese
templates around raw numbers, not prose. This session gives the tutor a
real degraded-mode text, matching the GOAT's.

### Contract

- New function in `narration.py`: `describe_assessment(assessment: Assessment, mover_color: str, language: str) -> str`.
  Same spirit as `describe_move`: deterministic, no model, phrase tables per
  language. Silent or one line for excellent/good (design.md §6's asymmetric
  commentary rule); for inaccuracy/mistake/blunder, states what was lost,
  what the stronger alternative was, and (blunder only) offers the take
  back -- the same four things the client template currently renders, just
  as a sentence instead of a client-side format string.
- Update narration.py's module docstring (and CLAUDE.md's one-line
  description of it) to cover both voices' degraded-mode text -- it already
  builds the opponent's commentary; this makes explicit that it also builds
  the tutor's.
- `coach.py` gains `narrate_assessment(assessment, mover_color, game, language) -> str`,
  same API-then-fallback shape as `narrate_goat_move`.
- `AssessmentResponse` gains a `commentary: str | None` field (`None` exactly
  when `tutor` itself is `None`).

### Tests

Same shape as session 2's: mocked success, mocked-failure-falls-back-to-
`describe_assessment`, no real network in the suite, one integration test
gated on a real key.

---

## 4. `web/`: render narrated prose, retire the client-side templates

Once the server always sends `commentary` (LLM prose or the deterministic
fallback -- either way, real sentences), the client no longer needs to
assemble tutor/GOAT text itself from raw fields.

### Contract

- `#status` shows `goat_move.commentary` instead of the current
  `"GOAT plays {san}"` line (the move itself -- SAN -- stays shown
  alongside it, just not as the whole message).
- `#tutor-panel` shows `tutor.commentary` instead of the client-built
  classification/best-move/continuation lines. The take-back-offer button
  (session 5 of week 3) is unaffected -- it still keys off
  `tutor.offer_take_back`, a boolean, not off any text.
- `web/i18n.js`'s per-move template strings (`goatPlays`, `tutorLine`,
  `betterWas`, `likelyContinuation`, `mistakeCountsLine`'s label lookups for
  classification words) are removed once nothing calls them -- static UI
  labels (buttons, dropdowns) and the mistake-count/summary panels (still
  server-structured numbers, no prose from coach.py this week) keep their
  entries.

### Tests

Manual, same as every `web/` session before it: play a move in each
language, confirm the shown text is the server's prose, confirm a blunder's
take-back button still appears and still works, confirm degraded mode
(temporarily unset `ANTHROPIC_API_KEY`) still shows sane deterministic
sentences in both languages, not an empty panel.

---

## 5. Mate badge

design.md §7. `engine.py` already distinguishes `mate_in` from `score_cp`
per candidate (week 1) -- this session is entirely about surfacing it and
building the badge, no `engine.py` changes.

### Contract

- `GameStateResponse` gains `mate_in: int | None` -- positive when the user
  has the mate, negative when facing it, `None` otherwise. Read off the
  user's own best candidate each `/move`/`/new-game` response (the same
  analysis already computed for the evaluation number -- no extra Stockfish
  call).
- Badge is discreet, above the board, states existence and distance only --
  "mate in 3 available" / "you are facing mate in 2" -- never the piece,
  square, or move (design.md §7's central rule; do not let `best_move`
  leak into the badge's own text even when it happens to be the mating
  move).
- Its own on/off switch, persisted like theme/language (`localStorage`),
  default on.

### Tests

- Positions with known forced mate in 2, 3, and 5 (hand-built FENs,
  integration-marked since they need Stockfish): `mate_in` reads correctly
  in both directions.
- The badge's own text-building function (pure, client-side or a small
  server helper -- whichever session 5 lands on) never contains a square
  name or piece letter for a genuine mate-in-N case.
- The switch, off, hides the badge with mate_in still present in the raw
  response (server always computes it; the switch is purely a display
  choice, same pattern as the theme).

---

## 6. Evaluation bar

design.md §8: "Evaluation bar on the side, with a hide option." The number
already exists in every response (week 2); nothing renders it as a bar yet.

### Contract

- A vertical bar alongside the board, filled proportionally to the
  (user-perspective) evaluation, saturating past some bound (mate or a
  large cp value shouldn't produce an absurd sliver or an absurd overflow).
- A hide toggle, persisted like the mate badge's switch.
- Bar orientation follows board orientation (user's side visually "up"),
  consistent with "pieces at the bottom" already being color-dependent.

### Tests

Manual: play as both colors, confirm the bar reads correctly signed (more
filled toward the user's side when they're ahead), confirm the hide toggle
works, confirm a mate-in-N position saturates the bar sensibly rather than
crashing or rendering garbage width.

---

## 7. Game plan panel

design.md §5's "Game plan": persistent text, rewritten only on structural
transitions (queens traded, a file opens, pawn structure shifts, an endgame
begins) -- not on every move like the tutor/GOAT panels. This is the most
open-ended session in this plan; the exact transition-detection rule isn't
designed yet and should be nailed down at the start of the session, not
assumed here.

### Contract (starting point, expect to refine)

- Transition detection needs a *before* and *after* game state to diff
  against -- `persona.py` is a pure, stateless function today
  (`choose(candidates, ...) -> Choice`, no history). Two shapes are on the
  table: (a) `persona.py` gains a pure comparison function taking both
  board states explicitly (still stateless -- a function of two inputs, not
  internal memory), or (b) `server.py` does the diffing itself, since it
  already holds the game's history and this is arguably orchestration, not
  style-selection logic. Decide this before writing code -- it changes
  `persona.py`'s public contract either way, which CLAUDE.md requires
  updating in lockstep.
- Once a transition fires, `coach.py` (or `narration.py`'s deterministic
  fallback) produces one to two sentences describing the new phase in plain
  language, in the player's chosen language.
- Server persists the current plan text across moves that don't trigger a
  transition (`app.state`, same lifetime as `mistake_counts`) and includes
  it in every `GameStateResponse`.
- Web UI: its own persistent panel area, distinct from both the GOAT's and
  the tutor's (three voices/areas on screen now, not two).

### Tests

- Transition detection: hand-built move sequences with a known queen trade,
  a known file opening, a known transition into a king-and-pawn endgame --
  each fires exactly once, at the right ply, and quiet moves in between
  don't refire it.
- The plan text persists (unchanged) across non-transition moves in the API
  response.

---

## 8. Stockfish crash resilience

The one unbuilt row of design.md §9's error-handling table: "Stockfish
crashes mid-game → restart the process and retry the analysis once. If it
persists, warn and pause." Today, `EngineUnavailable` is only handled at
server startup (`lifespan`) -- a mid-game crash currently has no recovery
path at all.

### Contract

- `server.py` (or `engine.py` itself) catches `EngineUnavailable` raised
  mid-game, restarts the `Engine` (a fresh subprocess, same construction
  path `lifespan` already uses), and retries the failed `analyse()` call
  exactly once.
- If the retry also raises `EngineUnavailable`, the game pauses rather than
  crashing the request: a clear error surfaces to the client (a distinct
  HTTP status or response shape from a plain illegal-move 400), and the
  game state is left exactly as it was before the attempted move -- nothing
  partially applied.

### Tests

- A faked process pipe (same style as `engine.py`'s existing nine tests)
  that raises on the first `analyse()` call and succeeds on the second:
  confirm the retry happens and the second result is what's returned.
- A faked pipe that fails twice: confirm the pause/error path, and that
  `game`/`assessment_history`/`mistake_counts` are unchanged from before the
  attempt (nothing partially committed).

---

## 9. v1 close-out

- Full suite green, including every integration test that needs a real
  Stockfish and (for sessions 2-3's gated tests) a real `ANTHROPIC_API_KEY`.
- `pytest -m "not integration"` still green with neither installed --
  unchanged requirement from week 2.
- One full game per color played manually in the browser, both languages,
  confirming: GOAT commentary, tutor commentary, mate badge (provoke a
  short forced mate), evaluation bar, game plan panel transitions, take-back
  offer, end-of-game summary -- everything built across weeks 3-4 working
  together in one sitting.
- One full game played with `ANTHROPIC_API_KEY` deliberately unset --
  degraded mode throughout, confirming CLAUDE.md invariant 5 (no code path
  blocks a game on network availability) end to end, not just per-function.
- README's status checklist: check off week 4. Update design.md if anything
  built here diverged from what it currently says (session 7 in particular
  is likely to, per its own "expect to refine" note).

---

## 10. Work order

| Session | Build | Done when |
|---|---|---|
| 1 | narration.py speaks both languages; language reaches the server | `/new-game` accepts and stores a language; narration.py's tests pass in both |
| 2 | `coach.py` GOAT voice | a live `/move` response's `goat_move.commentary` is real prose, falls back cleanly without a key |
| 3 | `coach.py` tutor voice | a live `/move` response's `tutor.commentary` is real prose, same fallback guarantee |
| 4 | `web/` renders prose, retires client templates | a played move shows server prose in both languages, degraded mode still sane |
| 5 | Mate badge | a known mate-in-N position shows the right badge text, never the move; switch works |
| 6 | Evaluation bar | bar fill matches the evaluation number, signed correctly for both colors; hide toggle works |
| 7 | Game plan panel | a scripted queen-trade/file-opening/endgame transition updates the panel exactly once, at the right ply |
| 8 | Stockfish crash resilience | a faked one-time crash recovers via retry; a faked persistent crash pauses cleanly, no partial state |
| 9 | Full suite green; two full manual games (with and without an API key), both colors | suite green; both games show sane output start to finish |

---

## 11. Definition of done

Every row of design.md §9's error-handling table has real code behind it.
Both voices narrate in prose, in both languages, and degrade gracefully.
The mate badge, evaluation bar, and game plan panel all exist and match
their design.md descriptions (or design.md is corrected to match a
deliberate change, per CLAUDE.md's own rule). Full suite green. v1, as
README's status list defines it, is complete.

---

## 12. Not this week

- Styles beyond Carlsen, weight calibration, an opening book, Maia, a
  free-text instruction field, saved games/statistics, PGN import,
  packaging -- all still explicitly out of scope per design.md §11 and
  CLAUDE.md's Scope section. Nothing here changes that.
- Deciding "how many mistakes is too many" (design.md §6's open question) --
  still pending a chess teacher's input; the tutor keeps commenting on
  every qualifying mistake, unchanged.
- Any second narration language beyond en-US/pt-BR.
