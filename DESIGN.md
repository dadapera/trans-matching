---
name: Trans Matching
description: Agente contabile — carta vs gestionale
colors:
  bg: "#0f1117"
  bg-elevated: "#171b26"
  bg-panel: "#1c2230"
  border: "#2a3344"
  text: "#e8ecf4"
  text-muted: "#8b95a8"
  accent: "#5b8def"
  accent-hover: "#7aa3f5"
  success: "#3ecf8e"
  warning: "#f0b429"
  danger: "#f07178"
typography:
  display:
    fontFamily: '"DM Sans", system-ui, sans-serif'
    fontSize: "1.35rem"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: '"DM Sans", system-ui, sans-serif'
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: '"DM Sans", system-ui, sans-serif'
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '"DM Sans", system-ui, sans-serif'
    fontSize: "0.8rem"
    fontWeight: 600
    letterSpacing: "0.06em"
  mono:
    fontFamily: '"JetBrains Mono", ui-monospace, monospace'
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  panel: "10px"
  pill: "999px"
spacing:
  xs: "0.35rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.25rem"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: "0.55rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: "0.55rem 1rem"
  button-danger:
    backgroundColor: "rgba(240, 113, 120, 0.15)"
    textColor: "{colors.danger}"
    rounded: "{rounded.lg}"
    padding: "0.55rem 1rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "0.55rem 1rem"
  panel:
    backgroundColor: "{colors.bg-panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "{spacing.lg}"
---

# Design System: Trans Matching

## Overview

**Creative North Star: "The Audit Console"**

Trans Matching reads as a calm, traceable control room for accounting reconciliation — not a marketing site, not a spreadsheet clone. The interface is dark, information-dense, and built for long sessions: an accountant uploads documents, watches live agent activity, and inspects match outcomes before posting. Visual energy stays low; status color and left-edge accents carry meaning when something needs attention.

Surfaces stack in three tonal steps (page → header/tabs → panels) with hairline borders instead of heavy shadows. Interaction feedback is gentle — soft accent tints on hover, pill badges for run state, gradient progress fills — so high-volume review does not feel alarming. JetBrains Mono appears wherever identifiers, trace IDs, and SIAP codes need to scan.

**Key Characteristics:**

- Dark three-tier surface stack with border-defined depth, not shadow-defined depth
- Signal Blue accent reserved for primary actions, active tabs, and in-progress state
- Semantic status palette (green / amber / red / muted) applied consistently across badges, table rows, and trace cards
- Uppercase micro-labels for panel sections and table headers; sentence case for body and controls
- Sidebar + main split layout optimized for Operate mode: controls left, live feed and report right
- Italian copy throughout; monospace for machine-readable values

## Colors

A restrained cool-dark palette: near-black bases, blue accent, and traffic-light semantics for match outcomes.

### Primary

- **Signal Blue** (`#5b8def`): Primary buttons, active tab underline, dropzone hover, progress bar fill, link actions, in-progress trace state. The only hue that reads as "go / active."
- **Signal Blue Hover** (`#7aa3f5`): Hover state for primary controls and range-slider thumbs.

### Neutral

- **Midnight Base** (`#0f1117`): Page background, sticky table header backdrop.
- **Elevated Slate** (`#171b26`): Header bar, tab strip, run-history item default, range-slider thumb fill.
- **Panel Slate** (`#1c2230`): Sidebar panels, trace cards, mode-switch track, report stat chips.
- **Steel Border** (`#2a3344`): Panel borders, table dividers, progress track, timeline connectors.
- **Cloud Text** (`#e8ecf4`): Primary body and heading text.
- **Ash Muted** (`#8b95a8`): Subtitles, hints, inactive tabs, secondary metadata.

### Semantic (status, not brand)

- **Match Green** (`#3ecf8e`): Successful match, high confidence, completed run, positive counts.
- **Caution Amber** (`#f0b429`): Ambiguous match, medium confidence, stopped run, alternatives.
- **Alert Coral** (`#f07178`): Errors, failed runs, danger actions, unmatched critical issues.

Semantic colors appear at low opacity (≈15–20%) as badge backgrounds and at full strength for text and left-edge accents.

### Named Rules

**The Semantic Edge Rule.** Match outcome is communicated with a 3px left border on trace cards and tinted table row backgrounds — never by recoloring the entire card background.

**The Accent Sparingly Rule.** Signal Blue marks interactive focus and progress. It does not decorate static content; if nothing is actionable, the screen should read mostly neutral.

## Typography

**Display Font:** DM Sans (with system-ui fallback)  
**Body Font:** DM Sans (with system-ui fallback)  
**Label/Mono Font:** JetBrains Mono (with ui-monospace fallback) for run IDs, trace chips, code snippets, and tabular identifiers

**Character:** DM Sans gives a modern, neutral sans feel — approachable without feeling consumer-playful. Mono is reserved for data the accountant will copy or cross-reference against SIAP.

### Hierarchy

- **Display** (600, 1.35rem, 1.3): App title in header only ("Trans Matching").
- **Title** (600, 1rem, 1.4): Trace card transaction headings, emphasized row metadata.
- **Body** (400, 0.9rem, 1.5): Buttons, tabs, dropzone labels, feed copy. Primary reading size.
- **Label** (600, 0.8rem, uppercase + 0.06em tracking): Panel section titles (`Documenti`, `Analisi`), table column headers.
- **Mono** (400, 0.75–0.8rem): Run IDs, filter trace codes, gestionale identifiers, `pre` blocks in trace details.

### Named Rules

**The Panel Label Rule.** Section titles inside `.panel` are always uppercase micro-labels in Ash Muted — they label regions, they do not compete with content.

**The Mono for Machines Rule.** Any value that might be pasted into SIAP or searched in logs uses JetBrains Mono; prose reasoning stays in DM Sans.

## Layout

Two-column **Operate** shell: fixed **320px sidebar** (upload, transaction range, run controls, history) + fluid **main** (tabbed live feed / report). Below **900px**, the grid collapses to a single column (sidebar stacks above main).

Vertical rhythm uses **1rem** gaps between sidebar panels and **1rem** padding inside panels. The main area is a flex column: tab bar (fixed height) + scrollable tab panel. Live feed and report table manage their own internal scroll; the page does not scroll as a whole on desktop.

Density is medium-high: compact table cells (0.55rem padding), small badges (0.75rem type), but panels breathe with 1rem internal padding. Empty states center with 3rem vertical padding.

## Elevation & Depth

**Tonal flat.** Depth is conveyed by surface stepping (`bg` → `bg-elevated` → `bg-panel`) and 1px `border` lines. No drop shadows on panels, buttons, or sidebar items.

The one exception: **trace cards** carry a soft ambient shadow (`0 10px 30px rgba(0,0,0,0.12)`) to lift transaction timelines slightly above the feed — the only "floating" element in the system.

Focus and hover deepen through border-color shifts (accent at ~55% opacity) and light accent washes (`rgba(91,141,239,0.06–0.12)`), not elevation change.

### Named Rules

**The Flat-By-Default Rule.** Surfaces are flat at rest. The trace card shadow is the sole structural lift; everything else uses tone and border.

## Shapes

Corners are **gently rounded**, never pill-shaped except badges and segmented controls.

- **Panels:** 10px radius (`--radius`)
- **Buttons, dropzones, trace cards, details blocks:** 8px
- **Report stat chips, run-history items:** 6px
- **Trace chips, inline code:** 4px
- **Status badges, mode-switch, progress bar:** full pill (999px)

Borders are 1px solid `Steel Border`; dashed borders on dropzones. Danger buttons use a soft fill + matching border at 35% opacity rather than solid red fills.

## Components

Operational, refined-calm: clear affordances, muted default state, gentle transitions (≈150ms on background/border).

### Buttons

- **Shape:** 8px radius, inline-flex with icon gap 0.4rem
- **Primary:** Signal Blue fill, white text, 0.55rem × 1rem padding. Hover → Signal Blue Hover. Disabled → 45% opacity.
- **Danger:** Translucent coral fill + coral border; used for Stop. Never solid red.
- **Ghost:** Transparent + border; report export and secondary actions. Hover → accent wash + accent border.
- **Block:** Full-width primary for upload confirm.

### Chips / Badges

- **Status badge:** Pill, uppercase 0.75rem, semantic tinted background (20% opacity) + full-strength text color. Spinner inside for running/stopping.
- **Trace status:** Same pill language on trace cards (running / matched / ambiguous / unmatched / error).
- **Report stat:** 6px radius, bordered chip; active state uses accent ring (`box-shadow: 0 0 0 1px accent`) not fill swap.
- **Mode switch:** Pill track with nested pill active segment (debug toggle in live feed).

### Cards / Containers

- **Panel:** Panel Slate background, Steel Border, 10px radius, 1rem padding. Section `h2` as uppercase label.
- **Trace card:** Panel styling + left semantic border + optional ambient shadow. Hover/focus border shifts to accent.
- **Dropzone:** Dashed border, 8px radius; hover/drag → accent border + 6–10% accent wash.

### Inputs / Fields

- **Range slider:** Dual-thumb custom control; 6px track, 18px circular thumbs with accent border on Elevated Slate fill. Selected range shows accent gradient.
- **File input:** Hidden; entire dropzone is the hit target (click + drag). Keyboard: Enter activates.
- **Tabs:** Text buttons with 2px bottom border; active tab → Cloud Text + accent underline.

### Navigation

- **Tab bar:** Elevated Slate background, bottom border, no side padding on tabs beyond 1rem container.
- **Run history:** Vertical list of 6px-rounded items; hover/active → accent border + light accent wash. Run ID in mono.

### Trace Timeline (signature component)

Agent activity renders as a vertical timeline inside trace cards: 24px circular step icons connected by 1px border lines, tool/success/error coloring on icons, collapsible `<details>` for raw debug output in mono `pre` blocks. This is the system's most distinctive pattern — preserve it for any new observability UI.

## Do's and Don'ts

### Do:

- **Do** use the three-tier surface stack (`#0f1117` / `#171b26` / `#1c2230`) for page, chrome, and content panels.
- **Do** communicate match outcomes through left-edge accents and subtle row tints, not full-card background floods.
- **Do** keep primary actions in Signal Blue; reserve green/amber/red for semantic status only.
- **Do** use uppercase 0.8rem labels for panel sections and table headers.
- **Do** use JetBrains Mono for run IDs, trace IDs, SIAP identificativi, and debug output.
- **Do** keep transitions at ~150ms for hover/focus; prefer border and background shifts over scale or shadow.

### Don't:

- **Don't** add shadows to panels, sidebar items, or buttons — trace cards are the only lifted surface.
- **Don't** use solid saturated red or green button fills; danger is always translucent coral.
- **Don't** introduce a second accent hue; Signal Blue is the sole interactive color.
- **Don't** switch to a light theme without an explicit redesign — the incumbent system is dark-only.
- **Don't** use decorative illustration or marketing hero patterns; this is Operate-mode tooling.
