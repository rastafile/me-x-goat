# UI reference — "Grandmaster Ledger"

A visual reference for the interface redesign planned in `docs/week-5.md`,
generated with Google Stitch and hand-corrected in this conversation.

- `mockup.html` — a static HTML/Tailwind mockup of the redesigned screen.
  **Not shipped code.** It's a standalone reference for spacing,
  typography, and hierarchy — see the caveats below before treating
  anything in it as ready to copy into `web/`.
- `DESIGN-SYSTEM.md` — the design system Stitch generated alongside the
  mockup: palette, type scale, spacing, shape language. Still accurate as
  of this writing; the corrections below were structural/content fixes,
  not palette changes.

## What was corrected from Stitch's raw output before this became the reference

- Chess pieces were originally AI-generated sketch images (illegible) —
  replaced with real Unicode chess glyphs for the mockup's own purposes.
  **Not relevant to the real app**: `web/` already renders the board
  through the vendored `cm-chessboard`, which has its own real piece set
  (`web/vendor/cm-chessboard/assets/pieces/standard.svg`) across all five
  existing board themes. Nothing about board/piece rendering needs to
  change.
- A bottom navigation bar (grid/notes/brain/profile icons) was removed —
  this is a single-screen local app, no accounts, no other pages.
- The three "voice" panels were reordered to tutor → opponent → game plan
  (chronological: the tutor reacts to the user's own move before the GOAT
  ever replies, and the tutor is the app's core reason to exist).
- The mate badge and evaluation bar were added/fixed (the eval bar was
  originally 1px wide with a transparent fill on one side; a mate-forcing
  example was left un-saturated at first, since fixed to fill fully).
  Both are plain, un-boxed elements, matching the rest of the page.
  Read `web/app.js`'s `renderEvalBar`/`renderMateBadge` for the exact
  saturation/clamping rules — the mockup's numbers are illustrative only.
- The settings drawer's style/theme dropdowns originally listed options
  that don't exist in the real app (styles "Tal"/"Karpov" beyond Carlsen;
  themes "Classic"/"Minimal" instead of the real five). Corrected to match
  `web/index.html`'s actual `<select>` options exactly.

## What implementation must resolve, not copy verbatim

`mockup.html` loads Tailwind and two fonts (Libre Caslon Text, Hanken
Grotesk) from CDNs (`cdn.tailwindcss.com`, `fonts.googleapis.com`) at
runtime. **The real app cannot do this as-is**: "Everything runs on your
machine... Offline play is a requirement, not a fallback" (README/
design.md). `web/` currently has zero runtime network dependencies beyond
the narration API itself (which already degrades gracefully offline).
Session 0 of `docs/week-5.md` resolves this — see that plan for the
decision (vendoring fonts locally, or a system-font fallback stack, and
hand-written CSS replacing Tailwind's utility classes, matching how
`cm-chessboard` was vendored for the identical reason).
