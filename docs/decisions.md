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
