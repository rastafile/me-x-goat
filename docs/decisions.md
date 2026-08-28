# Decisions

Architecture decision records for choices that would look arbitrary, or
reversible, from reading the code alone — why we did *not* do the obvious
alternative.

---

## ADR 1: Raw UCI dialogue, not python-chess's SimpleEngine

### Context

`docs/week-1.md`'s original plan for `engine.py` was to write the raw UCI
dialogue once, to understand it, then switch to `chess.engine.SimpleEngine`,
which handles the same traps (perspective, MultiPV, mate vs. cp, killing the
process) without needing to get them right by hand.

By the time that switch would have happened, the raw dialogue had actually
been hardened — closed-pipe detection, idempotent shutdown, the
`Analysis`/`loss_cp` layer — and had nine tests built against a faked process
pipe, verified against real Stockfish.

### Decision

`engine.py` stays on the raw UCI dialogue. `python-chess` still enters the
project, through `game.py`, where the payoff is real: the rules are the
tedious part, not the protocol.

### Rejected alternative

Switching to `SimpleEngine` as originally planned. Rejected because by the
time the switch would happen, it would only discard working, tested code and
require rewriting those tests around a different internals surface — to save
UCI plumbing that was already done and already correct.

---

## ADR 2: Announce mate's existence and distance, never the move

### Context

Stockfish detects forced mate natively and reports the distance instead of a
centipawn score. The question is how much of that to surface: showing
nothing wastes real signal Stockfish already has; showing the winning move
outright turns a chess lesson into an answer key.

### Decision

A discreet badge announces that mate exists and how far away it is, in both
directions ("mate in 3 available", "you are facing mate in 2") — never the
piece, the square, or the move. The badge has its own switch, so a user can
wean themselves off it. The actual solution only appears through the tutor,
after the user has moved, whether they found it or not.

### Rejected alternative

Surfacing the mating move or sequence directly once detected (or highlighting
the relevant pieces/squares). Rejected because it replaces the user's own
search with the app's: announcing that a solution exists is pedagogical,
handing over which move it is is not — the badge is a tactics-puzzle-book
prompt, not the answer.

A badge with no switch at all was also considered and rejected: left on
indefinitely, the user stops scanning the position for mate themselves and
starts waiting for the warning instead. The skill never forms.

---

## ADR 3: Regulate strength with a tolerance margin, not Stockfish's Skill Level

### Context

The GOAT's strength must be adjustable (800–2800) without the persona losing
its recognizable style — a weakened opponent that plays nothing like Carlsen
at any strength defeats the point of a styled opponent at all.

### Decision

One strength parameter controls two things: Stockfish's analysis time per
move, and the width of `persona.py`'s tolerance margin (how many centipawns
below the best candidate is still eligible for style scoring). A wide margin
means choosing among moves that are good but not optimal — this lowers
playing strength while keeping the exact same style-scoring machinery active
at every level.

### Rejected alternative

Using Stockfish's own built-in strength throttling (`Skill Level` /
`UCI_LimitStrength`/`UCI_Elo`) to weaken the engine directly. Rejected
because that throttling degrades move quality in ways decoupled from the
GOAT's own style heuristics — a Stockfish weakened this way plays worse
chess, not "Carlsen playing worse chess." The margin-based approach keeps
`persona.py`'s heuristics scoring the same kind of candidate set at every
strength; only how many candidates qualify changes.

---

## ADR 4: The tutor never sees the GOAT's internal state

### Context

`tutor.py` and `persona.py` both analyze the same engine output but for
different purposes: `persona.py` picks the opponent's move, `tutor.py`
judges the user's. If the tutor could see the GOAT's chosen move, its tags,
or its reasoning before the user has finished forming their own view of the
position, its commentary could leak the opponent's plan.

### Decision

`tutor.py` receives only the position and the engine's candidates. Its
function signature has no path for the GOAT's move, tags, or `Choice` to
reach it, ever.

### Rejected alternative

Giving the tutor access to the GOAT's chosen move or tags, e.g. to let it
cross-reference "the opponent is aiming for X, did you see it?". Rejected
because that is exactly the leak the tutor's independence exists to prevent
— it would let the "independent" tutor quietly do the opponent's talking for
it. If a future signature starts requiring that access, the design is wrong,
not the signature.

---

## ADR 5: Style stays a move-time filter, not a repertoire, for v1

### Context

`persona.py` models the GOAT's style as a move-time preference: given the
engine's candidates for the current position, hand-written heuristics score
each one on things like trading queens while ahead, steering toward
endgames, keeping central tension, and avoiding chaotic lines. Nothing about
which openings the GOAT plays is modeled at all.

### Expert input

A chess teacher consulted for this project pushed back on that framing. Her
position, verbatim in substance: she recognizes a player by knowing what
they play — the opening repertoire, not traits visible in individual moves.
Style lives in the repertoire, and it is not fixed: it is what a player
studies, and it shifts over their lifetime.

### Decision

Keep the move-time filter for v1. It produces a recognizable character —
this is what the five Carlsen heuristics in design.md §5 already do — which
is enough for a learning tool whose job is teaching chess, not modeling a
specific player's career.

### Known limitation

This is a caricature of style, not style itself. The heuristics make an
opponent recognizably prefer trades, or avoid mess, move to move — they say
nothing about which openings the GOAT reaches for, which is where the
expert's account says a player's identity actually lives.

### Rejected for now

An opening book — steering the persona toward a specific, curated
repertoire — is the strongest lever for real style, and would be the actual
fix the expert's feedback points to. Out of scope for v1: design.md §11
already deferred an opening book for unrelated infrastructure reasons; this
ADR is the record that it also matters for style specifically, not only as
a nice-to-have, and that its absence is a known limitation of what "style"
means in this app, not a settled design choice.

**Superseded, week 6**: ADR 11 unlocks and builds this. This section
stays as the historical record of why it was deferred, not as a
currently-true statement of scope.

---

## ADR 6: The page's language switch is client-side, independent of `OUTPUT_LANGUAGE`

### Context

CLAUDE.md requires that "text shown to the end user is controlled by the
`OUTPUT_LANGUAGE` setting... Do not hardcode user-facing strings in any
single language." `OUTPUT_LANGUAGE` is documented (README) as a server
startup setting, intended for the narration API's output once `coach.py`
exists (week 4). But `coach.py` doesn't exist yet: every sentence the user
sees today is assembled entirely client-side, in `web/app.js`, from
structured data the server returns (a classification word, a cp number, a
UCI move, an outcome enum) — the server itself never emits a sentence.

### Decision

Add a language switch to the page (English / Português (Brasil)), backed by
a small client-side dictionary (`web/i18n.js`) and persisted the same way
the theme already is — `localStorage`, no server round trip. Every string
`app.js` shows the user, static labels and the dynamic tutor/mistake/summary
panels alike, is routed through this module; nothing is hardcoded to one
language, which satisfies CLAUDE.md's rule for everything the app actually
displays right now.

### Rejected alternative

Wiring the switch to `OUTPUT_LANGUAGE` instead of building a page-side one.
Rejected because `OUTPUT_LANGUAGE` is a server-process-wide startup setting
with no channel from the browser to it without a new endpoint, and because
it would fix the language for the whole server rather than letting whoever
is actually looking at the screen choose it per visit.

### Known limitation

When `coach.py` starts generating real narration server-side (week 4), it
will need to know which language to write in. The natural fix is for the
page's own choice (already persisted client-side) to become the value the
client sends the server as the requested narration language, with
`OUTPUT_LANGUAGE` remaining the *server's own* default for contexts with no
client attached (e.g. `play_cli.py`). That wiring doesn't exist yet and is
deferred to whichever week actually builds `coach.py` — not designed here,
per CLAUDE.md's scope rule against building ahead of the current plan.

**Resolved** in docs/week-4.md sessions 1-2, exactly this way:
`NewGameRequest.language` carries the page's choice to `app.state.language`;
`play_cli.py` reads `OUTPUT_LANGUAGE` directly, having no page of its own.

---

## ADR 7: `coach.py` enriches `narration.py`'s text, not `persona.py`'s raw tags

### Context

design.md §5 says `persona.py`'s tags "travel with the move all the way to
`coach.py`, which uses them as raw material for the text," so the
explanation matches the actual reason for the choice rather than a
rationalization invented by the model. Read literally, that would have
`coach.py`'s prompt hand the model raw tag identifiers and an evaluation
number, and ask it to write the sentence from scratch.

### Decision

`narrate_goat_move` computes `narration.py`'s deterministic text first (the
same text degraded mode would show) and asks the model only to *rephrase*
it more naturally, explicitly forbidden from adding any chess claim,
square, or move name not already in that note. The fallback path — no API
key, or any failure — returns that exact same text. The enriched and
degraded paths are therefore guaranteed to agree on substance; the model
only ever changes register, never content.

### Rejected alternative

Prompting directly from `persona.py`'s raw tags and evaluation. Rejected
because it reopens the exact risk design.md's "tags as raw material" rule
exists to close: a model asked to "explain why" from raw signals, in either
language, can still produce phrasing that reads as a *new* reason rather
than a restatement of an existing one. Wrapping `narration.py`'s own output
removes that degree of freedom — the same sentence a network outage would
show is the only material the model is allowed to riff on.

`narrate_assessment` (session 3, the tutor's voice) follows the identical
pattern over `describe_assessment`'s output instead — this decision covers
both voices, not just the GOAT's.

---

## ADR 8: Game-plan transition detection — `game.py` computes facts, `server.py` diffs them

### Context

design.md §5's game plan is rewritten only on a structural transition
(queens off, a file opens, an endgame begins), which needs a *before* and
*after* position to diff against. `persona.py` is pure and stateless
(`choose(candidates, ...) -> Choice`, no history) — it has no natural place
for a two-position comparison. `server.py`'s own module docstring says "No
chess logic lives here." Neither of the two shapes docs/week-4.md's
session 7 draft proposed (persona.py gaining a comparison function, or
server.py doing the diffing outright) is a clean fit as stated: the first
conflates style-selection with structural narration, the second reads like
exactly the "chess logic in server.py" the docstring rules out.

### Decision

Split it. `game.py` gains `phase_signature() -> PhaseSignature` — a
snapshot of plain facts about the *current* position (queens on board,
which files have no pawns, whether only kings and pawns remain) computed
from `self._board`. This keeps "game.py is the only module that touches
the board" (CLAUDE.md) intact: no other module ever calls into
python-chess to answer these questions itself.

`server.py` gains `_detect_transition(before, after) -> str | None`, which
diffs two `PhaseSignature` snapshots server.py already asked `game.py` for.
It only ever touches plain ints and frozensets — never `chess.Board`, never
a UCI move, never python-chess at all. That keeps it on the orchestration
side of the line the module docstring draws, the same side
`_evaluation_for_user` and `_mate_in_for_user` already stand on (reading
structured facts an object handed back, not deriving them from the rules
of chess itself).

### Rejected alternative

`persona.py` gaining a stateless pure comparison function
(`choose`'s sibling, taking two board states explicitly). Rejected because
detecting "the game's phase changed" has nothing to do with picking a
style-scored move — bolting it onto the module whose entire job is move
selection would make `persona.py`'s contract harder to read for a reason
unrelated to style, not easier.

Also rejected: `server.py` calling `chess.Board` methods directly to
inspect material and pawn structure itself, which is what "no chess logic
lives here" was written to prevent in the first place — `game.py` doing
that inspection and handing back a plain-data snapshot is what keeps the
line real instead of just aspirational.

### Known limitation

`/take-back` does not undo a game-plan transition. Popping the move that
triggered a phase change (e.g. undoing a queen trade) leaves the plan text
as whatever it last became, rather than reverting to what it said before —
unlike `mistake_counts`, which does get undone precisely via
`assessment_history` (week 3). Precise undo here would need its own
history stack (the transition text, and what it replaced, per ply), which
this session didn't build: the game plan is an occasional narrative aid,
not a fairness-affecting count, so a coarser fix was judged acceptable for
v1. Revisit if it turns out to look actively wrong in play rather than
just slightly stale.

---

## ADR 9: `web/`'s redesign vendors its two fonts locally instead of loading Tailwind/Google Fonts from a CDN

### Context

`docs/week-5.md` implements a UI reference (`docs/ui-reference/`) generated
with Google Stitch. As shipped, that reference's `mockup.html` loads
Tailwind and two Google Fonts (Libre Caslon Text, Hanken Grotesk) from
CDNs at runtime (`cdn.tailwindcss.com`, `fonts.googleapis.com`). README
and design.md: "Everything runs on your machine... Offline play is a
requirement, not a fallback." `web/` today has zero runtime network
dependencies beyond the narration API itself, which already degrades
gracefully offline (`coach.py`'s own fallback, design.md §9). Copying the
mockup's `<link>` tags verbatim would make the *page itself* — not just
narration — require internet access to render correctly, for the first
time in this project.

### Decision

Vendor both font families locally, the same way `cm-chessboard` was
vendored (design.md §3: "which also keeps the board working fully
offline, consistent with this app never needing anything but the
narration calls to leave the machine"). Both are SIL Open Font License —
freely vendorable, same licensing shape as `cm-chessboard`'s MIT — under
`web/vendor/fonts/`, referenced via local `@font-face` rules with real
system-font fallback stacks. No Tailwind at runtime either: `web/styles/`
stays hand-written plain CSS, translating the mockup's utility classes
into the project's existing convention (`base.css` for structure/chrome;
theme files stay board-square-only, untouched by this redesign).

### Rejected alternative

Loading the fonts (and Tailwind) from their CDNs directly, same as the
reference mockup does. Rejected because it would be the first thing in
this app that makes the page itself depend on network access — every
other network dependency (the narration API) was deliberately designed
with a full offline fallback from the start; the UI chrome doing
otherwise, just to save a vendoring step, would be a real regression in a
project that treats "runs entirely on your machine" as a repeated,
explicit selling point, not an implementation detail.

---

## ADR 10: `avoid_chaos`'s per-candidate scoring, and calibrating `WEIGHTS` from self-play data

### Context

`persona.py`'s `WEIGHTS` table (and `_MARGIN_TABLE`) were a week-1 guess,
never revisited — `CLAUDE.md`'s Scope section listed "weight calibration
(guess now, measure later)" as explicitly out of phase through week 5.
`docs/week-6.md` unlocks it: `tools/self_play.py` plays `persona.py`
against itself and reports how often each heuristic tag actually fires and
whether it changes the winning candidate.

180 self-play games across the six strength anchors (800-2800, 30 games
each, 18,565 plies total) surfaced two distinct findings:

1. `queen_trade` (weight 3.0, the highest) fired on 0.2% of plies;
   `keep_tension` (1.5) fired on 0.7%. Both conditions are narrow by design
   (an exact eval-range queen trade; a specific central-pawn-tension
   square) and rarely available among the engine's top-5 candidates in
   self-play. This is a firing-*condition* property, out of scope here —
   this session deliberately kept conditions untouched, weights only.
2. `avoid_chaos` (weight 1.0) fired on ~20-23% of plies across all six
   strengths — and was decisive (changed the winning candidate) exactly 0
   times out of 3,905 firings. Reading the code explains why: it computed
   the position's overall score spread (chaotic or not) but applied the
   resulting penalty *identically to every survivor*, never looking at the
   individual candidate being scored. A constant additive penalty shared by
   every option in an argmax comparison can never change which one wins, at
   any weight — this was not a calibration problem, it was a logic bug
   present since the heuristic was first written.

### Decision

Two changes, addressing the two findings differently:

- **`avoid_chaos` rewritten to be per-candidate.** It now penalizes each
  survivor in proportion to how far its own evaluation sits from the
  position's best-scored candidate, relative to the position's full spread:
  the calmest, top-scored option draws no penalty; the further a candidate
  deviates from the objectively best line, the more a chaotic position
  counts against it. Proven mechanically capable of changing a choice for
  the first time by a dedicated regression test
  (`test_avoid_chaos_can_change_which_candidate_choose_picks`), which uses
  a temporarily inflated weight to isolate the mechanism from the
  calibration question below.
- **`WEIGHTS["avoid_chaos"]` raised from 1.0 to 1.5**, matching
  `keep_tension`/`improve_worst_piece`'s "medium" tier (`design.md` §5) now
  that the weight has a real effect for the first time. Re-running the
  harness at 1.5 (800/1600/2400, 20 games each) still found 0 decisive
  firings out of 123. Rather than conclude the weight was still too low,
  a further exploratory run at 3.0 — `queen_trade`'s own "high" tier value,
  the highest in the table — found only 2 decisive firings out of 62
  (~3%) at strengths 1200/2000. Going from "mechanically incapable" (1.0)
  to "occasionally decisive even at the top of the scale" (3.0) confirms
  this is not a case of an under-weighted trait: `avoid_chaos`'s penalty
  can never disagree with the engine's own cp ranking (it always favors the
  higher-scored candidate, same direction the base tie-break already
  favors), so it can only ever *counteract* another heuristic's pull toward
  a worse-scored candidate — a real but narrow role by construction, not
  a symptom of insufficient weight. 1.5 keeps it correctly in its designed
  tier rather than inflating it into "high" territory for a few points of
  marginal effect.
- `queen_trade`, `toward_endgame`, `improve_worst_piece`, and
  `keep_tension`'s weights are unchanged — their self-play firing rates
  reflect narrow or permissive *conditions*, not miscalibrated weights, and
  this session deliberately kept conditions out of scope (see
  `docs/week-6.md`).
- `_MARGIN_TABLE` and `_CHAOS_SPREAD_CP` are unchanged — nothing in this
  data pointed at either needing adjustment.

### Rejected alternative

Raising `avoid_chaos`'s weight alone, without touching its scoring logic.
Mathematically impossible to work: a uniform penalty across every survivor
never changes an argmax comparison, at any weight — confirmed by the 0/123
result at 1.5 with the *fixed* logic already testing well above the
original weight, let alone the unfixed version.

### Known limitation

`queen_trade` and `keep_tension` remain rare in self-play (and, by the same
reasoning, in real games) because their firing conditions are narrow. Their
weights are correctly high/medium per `design.md` §5's own intent — they're
infrequently *applicable*, not infrequently *weighted*. Widening either
condition is a legitimate future change, deliberately deferred: this
session was scoped to weights only, and a condition change is a different
kind of decision (behavioral, not numeric) that deserves its own review.

`avoid_chaos` itself remains a rare, subtle influence even after the fix —
by design, not by accident: it only ever matters when another heuristic
is actively pulling toward a worse-scored, more volatile candidate in an
already-sharp position, which is an uncommon combination. This is a real
trait, correctly scoped, not a heuristic still waiting on more calibration.

---

## ADR 11: A curated opening book, superseding ADR 5's "Rejected for now"

### Context

ADR 5 (`docs/week-1.md`-era) kept `persona.py`'s style as a pure move-time
filter for v1, explicitly deferring an opening book — "the strongest
lever for real style" per the chess teacher consulted for this project —
as a known limitation, not a settled design choice. `CLAUDE.md`'s Scope
section listed "opening books" as out of phase through week 5.
`docs/week-6.md` Track B unlocks it, gated on the user supplying a real
PGN, which arrived as a single complete game (a tactical trap line: 1.Nf3
e5 2.Nxe5 exploiting a blunder, ending in a forced mate at move 16) —
confirmed by the user as the real repertoire content to ingest, not a
placeholder.

Building this also required reconciling it with `CLAUDE.md` invariant 1,
which read "every move decision comes from Stockfish" — a book move
comes from curated data instead, on the specific plies where it applies.
The user approved rewording the invariant before this session started:
the real rule is "never the language model," not "always Stockfish
specifically" — a book move is still data plus a deterministic lookup
rule, a second permitted *source* alongside Stockfish's own, always
validated legal before being played.

### Decision

- **New pure module, `src/opening_book.py`.** `next_move(move_history,
  color, style)` returns a UCI move or `None`. Matching is an exact
  move-sequence prefix — no transposition detection (recognizing the
  same position via a different move order) — confirmed with the user
  as an acceptable v1 limitation. Ties within a style resolve to the
  first matching line, deterministically; `persona.py` must stay a pure
  function, so no randomness is introduced here.
- **Lines are tagged by color, and only ever answer for that color.** A
  single ingested game naturally encodes both sides' moves, but only one
  side's choices are a real "repertoire" worth reproducing — in the
  supplied game, White's moves are the deliberate trap, Black's are just
  how an unprepared opponent responded to it, not something to imitate
  when the GOAT itself plays Black. Confirmed with the user that this
  PGN's content should still be ingested as-is; tagging it `color:
  "white"` only is what keeps a real design principle (a book represents
  intentional play) from being violated by this specific source game's
  nature. Data lives at `data/opening_books/<style>.json` — vendored,
  static, no runtime network, same principle as `web/vendor/fonts`
  (ADR 9) and `web/vendor/cm-chessboard`.
- **`persona.choose` gains an optional `move_history` parameter.**
  `None` (self-play tooling, any older caller) skips the book entirely —
  identical behavior to today. When provided, the book is consulted
  after the forced-mate check and before the heuristic filter, and a
  book move — when found — replaces the filter entirely for that ply
  (tagged `opening_book`, `reason_score=math.inf`, same convention as
  `forced_mate`) rather than competing inside it. Confirmed with the
  user: a book move represents a stronger, more specific preference than
  the heuristics approximate, so stacking the two added complexity with
  no clear benefit.
- **A forced mate still outranks a book move.** `_shortest_forced_mate`
  runs first, unconditionally, per `design.md` §7 — confirmed with the
  user this must hold even though it would essentially never matter in
  practice (mate this early in the opening is not realistic).
- **Book depth doesn't vary with strength.** Confirmed with the user:
  curated lines are short enough already that a separate "forget the book
  sooner at low strength" rule wasn't worth the added complexity for v1.
- **A book move is asserted legal before being returned**, independent of
  whether it happens to be one of Stockfish's own top-5 candidates for
  that position (it usually won't be — that's the point of consulting a
  book at all). A malformed or transposed entry fails loudly in testing
  via the assertion, not by playing an illegal move in production.
- `narration.py` gains an `opening_book` lead phrase in both languages,
  ranked alongside `forced_mate` at the top of `_LEAD_WEIGHTS` — the
  offline fallback path (`coach.py`'s own failure mode, design.md §9)
  must never be silent or wrong for this tag either.

### Rejected alternative

Waiting for a larger, more traditionally "curated" repertoire before
building any of this. Rejected because the user explicitly confirmed the
single supplied game should be treated as real content now, and the
architecture (a list of tagged, matched-by-prefix lines) scales to more
PGNs later without any change — there was no reason to gate the
*plumbing* on the *amount* of data behind it.

### Known limitation

The book currently has exactly one line, for White only — Black has no
book data at all, and will fall through to the heuristic filter on every
move regardless of what the opponent plays. This is expected, not a bug:
more lines (for either color) are a data addition to
`data/opening_books/carlsen.json`, not a code change.

---

## ADR 12: The optional chess clock is orchestration state, not board state

### Context

`docs/week-7.md` adds an optional chess clock. Confirmed with the user
before any code: presets only (no free-form minutes/increment input);
both sides timed identically, with the GOAT's own analysis time staying
exactly what it is today (no adaptive time management); a flagged side
loses unless the opponent has insufficient mating material (FIDE's own
rule); take-back never refunds time.

A real design question this raised: `python-chess`'s `Termination` enum
has no timeout value, and a clock is not a fact about a chess position --
`game.py`'s "only game.py touches the board" boundary (`CLAUDE.md`) has
nothing to say about it either way.

### Decision

- `src/clock.py` is new, small, and deliberately not pure in the way
  `persona.py`/`tutor.py` are (reading elapsed wall-clock time is a real
  side effect) -- but every method takes `now_ms` as an explicit
  parameter rather than reading the clock itself, keeping it
  deterministically testable, the same shape `engine.py`'s subprocess
  boundary already established for "not pure, but still testable."
- A clock-caused game end lives in `app.state.timeout_outcome`
  (`server.py`), not in `game.py`. `_state_response` is the one place
  that combines it with `game.is_over()`/`game.outcome()` into the
  response's `is_over`/`outcome` fields, so no caller has to remember to
  OR the two together itself.
- `GameStateResponse` gained a separate `ended_by_timeout: bool` rather
  than overloading `outcome`. `outcome` alone is ambiguous: a
  clock-triggered draw reuses the string `"insufficient_material"`
  verbatim (an ordinary board-reached draw already meant exactly that),
  so a client can't tell the two apart from `outcome` alone -- and it
  needs to, since `/take-back` treats them differently (below).
- `/take-back` rejects once `timeout_outcome` is set, but **not** for an
  ordinary board-ended game (a checkmate can still be taken back, per
  design.md's existing "no rating, no competition" philosophy). There is
  no rule invented here for "restoring time" to make a clock-ended game
  resumable, so it's simply not offered.
- Taking back into an in-progress position always restarts clock
  *tracking* for whoever is now to move (`Clock.start_turn`), regardless
  of whether a turn was already running. This is required, not
  cosmetic: a game-over move stops the clock with no turn running at
  all, and without an explicit restart, the mover's next real move after
  a take-back would go completely uncharged. Confirmed as a real
  regression, not a hypothetical one, by temporarily removing the fix
  and watching `test_take_back_after_checkmate_unfreezes_the_clock` fail
  exactly as predicted.
- The `outcome.timeout` phrase lives in `web/i18n.js`, not
  `narration.py`. This plan originally assumed the opposite -- but
  `narration.py`'s outcome phrases are only ever read from inside a
  GOAT-move response (`describe_move`), and a timeout never produces
  one (no move happens; time simply runs out). The existing client-side
  path that already covers "the user's own move ended the game, so
  there's no GOAT reply to narrate it" turned out to be the exact same
  mechanism a timeout needed -- discovered during session 1, not
  designed in this plan up front.

### Rejected alternative

Giving the GOAT adaptive time management (spending more real analysis
time on critical positions, budgeted against its own remaining clock).
Confirmed with the user as out of scope: at today's analysis times
(50-800ms/move), the GOAT will essentially never run low regardless of
time control, and building a real time-management policy has no
evidence behind it yet -- the same "guess now" trap week 6 spent two
sessions un-guessing for the style weights. If this ever becomes worth
doing, it deserves its own session-driven investigation, not a
first-pass guess bundled into this one.
