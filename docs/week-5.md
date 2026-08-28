# Week 5 — implementation plan

Goal: redesign `web/`'s chrome to match `docs/ui-reference/` (the
"Grandmaster Ledger" study-desk aesthetic), without touching how the board
itself is drawn. No server-side changes this week — every field this plan
touches already exists in `GameStateResponse` (weeks 3-4 built all of it);
this is presentation only.

Read `docs/ui-reference/README.md` before starting -- it documents exactly
what was corrected in the reference mockup and, more importantly, what
implementation must *not* copy verbatim (see session 0).

A real discovery from reviewing the reference: `web/` already renders the
board through the vendored `cm-chessboard`, which has its own real piece
set (`web/vendor/cm-chessboard/assets/pieces/standard.svg`) across all five
existing board themes (wood/classic-green/blue/marble/high-contrast). The
mockup's illegible pieces were a problem unique to its own from-scratch
board markup, generated for the mockup's own purposes -- nothing about
board or piece rendering needs to change here. This week is entirely about
the chrome around the board: header, settings, mate badge, evaluation bar,
and the three voice panels' order and typography.

---

## 0. Setup

### The CDN dependency `mockup.html` can't be copied as-is

`docs/ui-reference/mockup.html` loads Tailwind and two Google Fonts (Libre
Caslon Text, Hanken Grotesk) from CDNs at runtime. README/design.md: "Everything
runs on your machine... Offline play is a requirement, not a fallback."
`web/` currently has zero runtime network dependencies beyond the
narration API itself, which already degrades gracefully offline
(coach.py's own fallback). `cm-chessboard` was vendored specifically to
keep the board "working fully offline, consistent with this app never
needing anything but the narration calls to leave the machine"
(design.md §3) -- a Google Fonts / Tailwind CDN dependency for the page's
own chrome would break that same principle for the exact same reason.

**Decision**: vendor both fonts locally (Libre Caslon Text and Hanken
Grotesk are both SIL Open Font License -- freely vendorable, same
licensing shape as `cm-chessboard`'s MIT). No Tailwind at runtime either:
hand-write plain CSS in `web/styles/`, translating the mockup's utility
classes into the project's existing convention (one `base.css` for
structure/chrome, theme files staying board-square-only and untouched).
Record this as an ADR (mirrors ADR 8's shape: a real "would look
arbitrary from the code alone" decision) before writing any CSS.

### Contract

- New ADR in `docs/decisions.md` recording the above.
- Two font families vendored under `web/vendor/fonts/` (woff2, following
  `cm-chessboard`'s vendoring precedent), referenced via local `@font-face`
  rules in `base.css`. Real fallback stacks on both (a serif stack for
  Libre Caslon Text, a system-sans stack for Hanken Grotesk) so the page
  still reads correctly if a font file somehow fails to load.
- `base.css` gains the new palette as CSS custom properties (`--surface`,
  `--on-surface`, `--on-surface-variant`, `--outline-variant`, etc., named
  after `docs/ui-reference/DESIGN-SYSTEM.md`'s own token names) so later
  sessions reference tokens, not hardcoded hex values scattered around.

### Tests

Manual: load the app with network disabled entirely (airplane mode or
blocking the two font domains) -- confirm the page renders correctly with
the fallback stacks, nothing blocks on the fonts.

---

## 1. Header and collapsible settings panel

Replace the always-visible `<h1>` + `#new-game-panel` block with a slim
header (title, one settings icon) and a collapsible panel underneath it,
per the reference.

### Contract

- Header: title centered, a single "tune" icon button, right-aligned,
  toggling the settings panel open/closed. No second (hamburger) icon --
  this is a single-screen app with nothing for a hamburger to navigate to.
- Settings panel, collapsed by default: rows for color, strength, style,
  theme, language, mate-badge toggle, evaluation-bar toggle -- same
  content `#new-game-panel` already has today, restyled as label-left/
  control-right rows with hairline dividers, no boxes. Color as a
  segmented control (matches the reference); style/theme/language stay
  native `<select>` elements with exactly the app's real options (no
  invented styles or themes -- the reference mockup's own bug, corrected
  before it became the reference, but worth re-verifying against
  `web/index.html`'s current `<option>`s directly during implementation).
- Clicking a color button still starts a new game immediately (unchanged
  behavior from today) -- the panel doesn't gate that behind a separate
  confirm step.
- `data-i18n` labels carry over unchanged; nothing about `web/i18n.js`'s
  translation keys needs to change, only how they're laid out.

### Tests

Manual: panel opens/closes via the icon; every existing control (color,
strength, style, theme, language, both toggles) still does exactly what it
did before this session, just relaid out. Play a move with the panel both
open and closed -- confirm nothing about game state depends on panel
visibility.

---

## 2. Mate badge and evaluation bar restyle

Both are functionally correct already (`session 5` and `session 6` of
week 4) -- this is presentation only, no logic changes.

### Contract

- Mate badge: drop the pill/background treatment
  (`rgba(180, 140, 20, 0.15)` amber chip) for plain, small, muted text --
  matches the reference exactly. `renderMateBadge`'s logic in `app.js` is
  untouched; only `#mate-badge`'s CSS changes.
- Evaluation bar: restyle width/colors to the new palette (a light
  neutral track, ink-colored fill) -- `renderEvalBar`'s fill-percentage
  logic is untouched; only `#eval-bar`/`#eval-bar-fill`'s CSS changes.

### Tests

Manual: provoke a real mate-in-N position and a real mid-game evaluation
(same method used in week 4's own verification) -- confirm the restyled
elements still show the right text/fill, not just that they look right at
rest.

---

## 3. Voice panel reorder and restyle

### Contract

- Reorder `#tutor-panel`, `#status`, `#game-plan-panel` in `web/index.html`
  to tutor → opponent → game plan (chronological: the tutor reacts to the
  user's own move before the GOAT ever replies, and it's the app's core
  reason to exist -- `docs/ui-reference/README.md`'s own reasoning). Pure
  DOM reorder -- `app.js`'s `renderDynamicPanels` sets each panel's text by
  element ID and doesn't care about document order, so no JS changes
  needed for the reorder itself.
- Restyle away from the colored-card treatment session 5 of week 4 built
  (purple/teal left-border tinted boxes) toward the reference's
  typography-only differentiation: tutor centered and bolder, opponent
  left-aligned and normal weight, game plan right-aligned and light
  italic. The take-back-offer button (inside the tutor panel) keeps its
  own block-level layout rule from week 3's bug fix -- verify it still
  renders on its own line under the new styling, not squeezed back
  inline.
- "Take back" / "Export PGN" restyled as plain text links near the board,
  matching the reference -- same elements, same behavior, CSS only.

### Tests

Manual: play a move that triggers all three voices in one round (a
mistake with a take-back offer, on a round that also fires a game-plan
transition -- the same scripted scenario week 4's close-out session
already used) and confirm the new order and typography read correctly,
including the take-back button's own line.

---

## 4. Cross-theme check and close-out

### Contract

- Confirm the new chrome doesn't clash with any of the five board themes,
  particularly `high-contrast` -- that theme exists for accessibility
  (week 2 fixed a real contrast bug in it already); the new muted-grey
  text tokens must still meet a sane contrast minimum against the new
  ivory background, independent of which board theme is active.
- `pytest` suite: unaffected (this is `web/`-only), but run it anyway to
  confirm nothing server-side was accidentally touched.
- Update `design.md` §8 if the shipped interface diverges from its current
  wording once this is built (same close-out discipline session 9 of
  week 4 used).

### Tests

Manual: one full game per color, default theme and `high-contrast`, light
mode only (dark mode is out of scope this week -- see below), confirming
every piece built this week reads correctly together: header/settings,
mate badge, evaluation bar, all three voice panels in their new order,
take-back offer, end-of-game summary.

---

## 5. Work order

| Session | Build | Done when |
|---|---|---|
| 0 | Vendor fonts, palette tokens, ADR | page renders correctly with network disabled |
| 1 | Header + collapsible settings panel | every existing control still works, just relaid out |
| 2 | Mate badge + evaluation bar restyle | both show correct real data under the new styling |
| 3 | Voice panel reorder + restyle | tutor → opponent → plan, typography-only differentiation, take-back button still on its own line |
| 4 | Cross-theme check, close-out | one full game per color renders correctly under the new chrome, both default and high-contrast themes |

---

## 6. Definition of done

`web/`'s chrome matches `docs/ui-reference/` in spirit (exact pixel
parity isn't the goal -- the reference is a design system, not a
spec to trace). No new runtime network dependency. All five board themes
still readable, `high-contrast` still meets its accessibility purpose.
Full suite still green (unaffected, but confirmed).

---

## 7. Not this week

- Dark mode -- the reference mockup was only reviewed in light mode; a
  dark palette wasn't designed or approved, so it isn't built blind.
- Any change to board/piece rendering -- `cm-chessboard` already handles
  this correctly; not touched.
- Any server-side change -- every field this plan renders already exists
  in `GameStateResponse`.
- Any new board theme, style, or language -- still explicitly out of
  scope per `CLAUDE.md`'s Scope section, unrelated to this redesign.
