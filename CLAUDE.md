# Me X GOAT

A local chess study app. The user plays against an opponent with a grandmaster
persona and receives analysis from an independent tutor after each of their moves.

Full spec in `docs/design.md`. Weeks 1-6's plans are in `docs/week-1.md` through
`docs/week-6.md` (all done — v1 complete, the `web/` chrome redesign documented
in `docs/ui-reference/`, and week 6's data-driven weight calibration plus a
curated opening book, both deliberately unlocked from the Scope section
below). `docs/week-6-ux-quickfix.md` is a small out-of-band session (play
immediately on load) that ran alongside week 6. Current week's plan is in
`docs/week-7.md` (an optional chess clock, off by default). Read the spec and
the current week's plan before writing code. If this file and the spec
disagree, this file wins and the spec should be corrected.

## Invariants

These are not preferences. Breaking them breaks the product.

1. **The language model never chooses a move.** Every move decision comes from
   Stockfish's analysis or a curated, deterministic opening book, filtered by
   deterministic rules -- never from the language model. The model receives tags and
   numbers and returns prose. Any implementation where the model decides something
   about the game is wrong. An opening book move is still data plus a deterministic
   lookup rule, and it must always be legal in the current position -- it does not
   get an exception to "no model, no guessing," it is a second permitted *source* of
   candidate moves alongside Stockfish's own.
2. **Stockfish is never bundled.** It is an external binary the user installs,
   invoked as a separate process over UCI. This is what keeps the MIT license viable,
   since Stockfish is GPL-3. Do not vendor it, do not commit the binary, do not link
   against it.
3. **The tutor cannot see the persona's internal state.** `tutor.py` receives the
   position and the engine's candidates. It never receives the opponent's plan, tags,
   or choice. If a signature starts requiring that, the design is wrong.
4. **No integration with online chess platforms.** No client, no API, no browser
   automation, no live game import. The app is isolated by design.
5. **Games survive an API outage.** If narration fails, text is assembled from tags
   and evaluations. No code path may block a game on network availability.

## Evaluation perspective

A recurring source of bugs. Read this before touching evaluations.

- Stockfish reports scores from the perspective of **the side to move**.
- `engine.py` normalizes everything to **White's** perspective on the way in.
- Every internal module works in that convention. No exceptions.
- The flip to the user's perspective happens in **exactly one place**, at the
  server's output boundary.

If you find yourself flipping a sign anywhere else, stop. The bug is elsewhere.

## Architecture

One module, one responsibility. None of them import the server.

- `engine.py` — the only boundary with Stockfish. Returns an `Analysis` wrapping the
  candidate moves, each with either a centipawn score or a distance to mate, plus a
  `loss_cp` helper for how far a candidate sits behind the best one.
- `game.py` — game state. Wraps `python-chess`. Nothing else touches the board.
- `persona.py` — pure function. Picks the opponent's move from the candidates using
  style weights. No network, no state, no Stockfish.
- `tutor.py` — pure function. Classifies a move (excellent through blunder) by
  comparing an `Analysis` from before it and one from after it -- never touches
  `persona.py`. No network, no state.
- `narration.py` — pure functions. Builds both voices' commentary -- the opponent's
  from tags and an evaluation, the tutor's from an `Assessment` -- no model. This is
  the degraded-mode text `coach.py` falls back to when narration is unavailable, per
  the error-handling table in `docs/design.md`.
- `coach.py` — the only boundary with the narration API. Turns tags and numbers into
  prose, and falls back to `narration.py`'s text when the API fails.
- `server.py` — HTTP and orchestration. No chess logic.

`persona.py` and `tutor.py` are pure on purpose: that is what makes them testable
without network or cost. Do not introduce dependencies into them.

## Code style

- Python 3.11+. Type annotations on every public function.
- `@dataclass(frozen=True)` for data crossing module boundaries.
- Named domain exceptions (`IllegalMove`, `EngineUnavailable`), never a bare
  `Exception`.
- Moves are UCI internally. SAN only at presentation.
- No comments restating the code. Comments explain non-obvious decisions.

## Tests

- `pytest`. No test of `persona.py` or `tutor.py` may touch the network, the API, or
  Stockfish. Use hand-built candidate lists.
- Tests requiring Stockfish are marked as integration and may be skipped.
- Every chess edge case that comes up becomes a test: en passant, promotion, lost
  castling rights, threefold repetition, insufficient material, stalemate.
- The full suite must pass before any stage is called done.

## Scope

The week's plan defines what exists. Do not build ahead.

Not in this phase, however easy it looks:

- styles beyond Carlsen;
- Maia or alternative neural networks;
- packaging, Docker, deployment;
- performance optimization.

Weight calibration and an opening book were also on this list through week 5 --
week 6 unlocks both deliberately (see `docs/week-6.md` and `docs/decisions.md`
for the reasoning). Nothing else on this list is unlocked by that precedent;
each one needs its own explicit decision the same way.

If something seems necessary but sits outside the week's plan, ask before building it.

## Git

- One commit per coherent unit. Imperative mood, first line under 60 characters.
- Never commit with a red suite.
- `.venv/`, `__pycache__/`, and `.pytest_cache/` stay out of the repository.

## Language

Everything in this repository is written in English: code, names, comments, commits,
documentation, and issues.

Text shown to the end user is controlled by the `OUTPUT_LANGUAGE` setting, which
defaults to English. Do not hardcode user-facing strings in any single language.
