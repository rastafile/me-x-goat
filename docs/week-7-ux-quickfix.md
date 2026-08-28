# Week 7 UX quickfix — an explicit "Start game" button

A small, separately-scoped session, not part of `docs/week-7.md`'s own
sessions (all five are done). Prompted by real usage feedback: only the
color buttons started a new game. Changing any other setting (strength,
style, theme, clock) had no visible effect until a color was clicked
again — not obvious, and easy to mistake for a bug (a clock preset
selected but never applied, since the game already in progress predates
the change).

## Contract

- New `#start-game-button` at the bottom of `#settings-panel`, below the
  last toggle row. Starts a new game with whichever color is currently
  marked active, plus every other current setting (strength, style,
  clock) — the exact same call the auto-started game and a color click
  already make.
- Color buttons keep their existing behavior unchanged: clicking one
  still starts a game with that color immediately, no extra click
  required. This button is additive, for the common case of changing
  something *other* than color and wanting to apply it without touching
  color at all.
- Styled as the one clearly primary action on the panel — bolder text,
  set off by a rule above it — but still plain text, no box or pill,
  matching every other control here.

## Tests

Manual: change the clock preset (or strength, style, theme) without
touching a color button, click "Start game", confirm the new setting is
actually applied to the resulting game (verified live: selecting Bullet
and clicking Start game showed both clock displays with a Bullet-sized
budget, with color left at its existing selection).
