---
name: Grandmaster Ledger
colors:
  surface: '#fcf9f5'
  surface-dim: '#dcdad6'
  surface-bright: '#fcf9f5'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f3ef'
  surface-container: '#f0ede9'
  surface-container-high: '#eae8e4'
  surface-container-highest: '#e5e2de'
  on-surface: '#1c1c1a'
  on-surface-variant: '#444748'
  inverse-surface: '#31302e'
  inverse-on-surface: '#f3f0ec'
  outline: '#747878'
  outline-variant: '#c4c7c7'
  surface-tint: '#5f5e5e'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#1c1b1b'
  on-primary-container: '#858383'
  inverse-primary: '#c8c6c5'
  secondary: '#5e5e5b'
  on-secondary: '#ffffff'
  secondary-container: '#e1dfdb'
  on-secondary-container: '#63635f'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#0f0069'
  on-tertiary-container: '#7671ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e5e2e1'
  primary-fixed-dim: '#c8c6c5'
  on-primary-fixed: '#1c1b1b'
  on-primary-fixed-variant: '#474746'
  secondary-fixed: '#e4e2dd'
  secondary-fixed-dim: '#c8c6c2'
  on-secondary-fixed: '#1b1c19'
  on-secondary-fixed-variant: '#474744'
  tertiary-fixed: '#e2dfff'
  tertiary-fixed-dim: '#c3c0ff'
  on-tertiary-fixed: '#0f0069'
  on-tertiary-fixed-variant: '#321ed2'
  background: '#fcf9f5'
  on-background: '#1c1c1a'
  surface-variant: '#e5e2de'
typography:
  display-lg:
    fontFamily: Libre Caslon Text
    fontSize: 42px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Libre Caslon Text
    fontSize: 28px
    fontWeight: '600'
    lineHeight: '1.3'
  headline-md-mobile:
    fontFamily: Libre Caslon Text
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  game-plan-serif:
    fontFamily: Libre Caslon Text
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-base:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  label-caps:
    fontFamily: Hanken Grotesk
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.05em
  analysis-mono:
    fontFamily: jetbrainsMono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.4'
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  margin-page: 2rem
  gutter-panel: 1.5rem
  stack-sm: 0.5rem
  stack-md: 1rem
  stack-lg: 2rem
---

## Brand & Style

The brand personality is that of a quiet, sun-drenched study—scholarly, disciplined, and deeply analytical. This design system is built for the "quiet competitor," favoring the tactile sensation of a physical chess book and a well-organized desk over the high-octane stimulus of modern gaming. It evokes a sense of timelessness and intellectual rigor.

The visual style is **Minimalist with a Tactile twist**. It relies on generous whitespace (resembling wide book margins) and high-quality typography to organize information. Rather than heavy borders or bright gradients, depth is established through subtle paper-like textures and soft tonal shifts that suggest layers of physical parchment. The UI should feel like an extension of the board—functional, elegant, and unobtrusively professional.

## Colors

The palette is rooted in the "Study Desk" aesthetic, using low-strain, warm neutrals to facilitate long hours of analysis.

*   **Primary:** A deep, ink-like charcoal used for text and critical structural markers. It provides the "ink on paper" feel.
*   **Background (Surface):** A warm ivory/cream in light mode to mimic high-quality book paper. In dark mode, this transitions to a deep obsidian/parchment that retains a warm undertone to prevent eye fatigue.
*   **Coaching (Tutor):** A sophisticated, muted indigo used exclusively for the "voice" of the engine or tutor. It is authoritative yet calm.
*   **Game Plan (Strategy):** A soft, desaturated sage/teal. This color is used for structural shifts and strategic annotations, providing a clear visual distinction from tactical errors.
*   **The Board:** High-contrast classic wood themes (walnut and maple) are the default, ensuring the pieces (the "subjects" of the study) remain the focal point.

## Typography

This design system uses a dual-font strategy to balance the "bookish" aesthetic with analytical precision.

*   **Libre Caslon Text** is used for headers, game plan narratives, and titles. It brings a literary, traditional authority to the app. Use the italic variant for strategic notes to mimic margin annotations.
*   **Hanken Grotesk** is used for the functional UI, settings, and player data. It is contemporary and highly legible, ensuring the interface feels modern despite the traditional influences.
*   **JetBrains Mono** (Optional/Analytical): Use for PGN strings and raw evaluation numbers to maintain a clean, technical feel for data-heavy sections.

Text hierarchy is strictly enforced: large serif displays for high-level concepts, and clean sans-serif for interactive elements and data.

## Layout & Spacing

The layout philosophy is based on a **Fixed Grid** with generous "breathable" margins. The content should never feel cramped against the edges of the screen.

*   **Desktop:** A 12-column grid. The chess board occupies a 6-7 column span, with the analysis and coach panels occupying the remaining space.
*   **Mobile:** A single-column vertical stack. The board remains at the top, with "Voice Panels" appearing as cards below.
*   **Safe Areas:** Each primary functional block (Board, Analysis, Setup) is separated by "Air"—negative space that acts as a divider rather than using heavy lines. 
*   **The Setup Bar:** A collapsible horizontal or vertical strip that uses subtle background tints to separate itself from the main study area.

## Elevation & Depth

To maintain the "paper" aesthetic, this design system avoids heavy shadows and floating buttons.

1.  **Tonal Layering:** The primary background is the lowest level. Active panels or "Voice Panels" are placed on surfaces that are slightly lighter (in light mode) or darker (in dark mode) than the base background.
2.  **Soft Dividers:** Use 1px hairlines in a color only slightly different from the background (e.g., `#EAE8E3`) to separate sections.
3.  **Low-Opacity Shadows:** If elevation is required for a modal or a floating menu, use an extremely diffused, low-opacity shadow (e.g., `box-shadow: 0 4px 20px rgba(0,0,0,0.05)`).
4.  **The "Inset" Board:** The chess board should feel slightly recessed into the desk surface, achieved via a subtle internal 1px border.

## Shapes

The shape language is **Soft** and restrained. 

*   **Standard UI elements:** (Buttons, Input fields) use a `0.25rem` radius. This keeps the look crisp and professional without feeling "bubbly."
*   **Voice Panels & Cards:** Use `rounded-lg` (0.5rem) to provide a gentle, distinct container for coaching text.
*   **Mate Badges:** Use a pill-shape (full rounding) to make them instantly recognizable as status indicators.

## Components

*   **Voice Panels (Tutor & Plan):** These are the heart of the analytical experience.
    *   *Tutor Style:* Background tint of subtle Indigo (3% opacity), 4px solid Indigo left border.
    *   *Plan Style:* Background tint of subtle Sage (3% opacity), 4px solid Sage left border.
*   **Evaluation Bar:** Slim (8px wide), vertically oriented next to the board. Use Primary Charcoal and White—no bright reds or greens to maintain the neutral aesthetic.
*   **Chip-Style Mate Badges:** Small, high-contrast badges (White text on Primary Charcoal) that appear next to moves.
*   **Buttons:** 
    *   *Primary:* Outlined with a 1px Primary Charcoal border. No fill.
    *   *Secondary:* Text-only with an underline on hover, mimicking a hyperlink in a digital document.
*   **Chess Board:** Squares should be matte, not glossy. High-contrast themes should use the Ivory/Charcoal palette to match the UI perfectly.
*   **Collapsible Setup Bar:** Uses an icon-only trigger; when expanded, it reveals a clean list of toggles using the `label-caps` typography style.