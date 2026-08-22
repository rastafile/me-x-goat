# Contributing

Suggestions are the reason this repository is public. Open an issue describing what
you would change and why. Ideas that get implemented are credited in the commit and
in the release notes.

## Before you open a pull request

Read `docs/design.md`. It explains the decisions that are not obvious from the source,
and most disagreements about this project turn out to be disagreements with something
already argued there.

Five invariants are not open for negotiation. They are listed in `CLAUDE.md`, and the
short version is:

1. The language model never chooses a move.
2. Stockfish is never bundled with this project.
3. The tutor cannot see the opponent's internal state.
4. No integration with online chess platforms, ever.
5. Games keep working when the narration API is unavailable.

A pull request that breaks any of these will be declined regardless of how well it is
written.

## Standards

- Python 3.11+, type annotations on public functions.
- `pytest` suite green before you push.
- Tests for `persona.py` and `tutor.py` must not touch the network or Stockfish.
- Commit messages in the imperative mood, first line under 60 characters.
- Everything in the repository is written in English.

## Good first contributions

- Chess edge cases that are not yet covered by tests.
- Board themes — each one is a single CSS file.
- Style heuristics for personas other than Carlsen, once the structure is calibrated.
- Translations of user-facing strings.

## Reporting a bug

Include the FEN, the move, what you expected, and what happened. A position is worth
more than a paragraph.
