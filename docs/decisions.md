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
