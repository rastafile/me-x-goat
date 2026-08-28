# Week 6 UX quickfix — play immediately on load

A small, separately-scoped session, not part of either week-6 track (weight
calibration, opening book) — those stay paused, tracked in `docs/week-6.md`.
Prompted by real usage feedback: on load, the board shows the starting
position but there is no live game and no move input enabled until the user
opens the settings drawer and picks a color. Style, theme, and language are
also only reachable from behind that same drawer.

## Root cause

`web/app.js`'s init block (the code that runs at module load, after the
`Chessboard` is constructed) restores theme/language/badge/eval-bar settings
from `localStorage`, but never calls `startNewGame()` -- that only happens
from a color button's click handler. So the page always loads into a dead
state: pieces visible, nothing playable, and the one way out is undocumented
(the header's settings icon has no label, just an icon).

## Contract

- At the end of `web/app.js`'s init block, call `startNewGame()` with
  whichever color is already marked `.is-active` in `#color-choices`
  (`white` by default, matching the settings panel's own visual default) --
  same function, same request shape a color-button click already produces.
  No new endpoint, no new server-side behavior.
- This resolves the "can't play immediately" complaint directly. It also
  resolves "style choice isn't visible enough" as a side effect: the
  friction wasn't that the style `<select>` is hard to find once you're
  looking at the settings panel (it's a labeled row like every other
  control there) -- it was that nothing forced anyone to open that panel at
  all before this fix. No separate change to the style control itself.
- The settings panel stays collapsed by default, as week 5 designed it --
  changing color/style/theme/language mid-session still works exactly as
  before (a color click still starts a fresh game immediately).

## Tests

Manual: load the page fresh (cleared `localStorage`, or a private window) --
the board is playable immediately, no click required. Confirm take-back and
export-pgn are enabled once a real move is made, exactly as they are for a
game started via the color buttons today. Confirm changing color/style/theme/
language after this auto-started game still behaves exactly as before.
