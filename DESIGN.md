---
name: Trans Matching
description: Agente contabile — carta vs gestionale
colors:
  bg: "#f3efe6"
  bg-accent: "#e4ddd0"
  panel: "#fffdf8"
  ink: "#1c1a16"
  muted: "#5c564c"
  line: "#c9c0b0"
  btn: "#1c1a16"
  btn-ink: "#f3efe6"
  ok: "#1f6b3a"
  warn: "#8a3b12"
  danger: "#9b2c2c"
typography:
  display:
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif'
    fontSize: "1.35rem"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  title:
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif'
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.4
  body:
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif'
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif'
    fontSize: "0.9rem"
    fontWeight: 650
  mono:
    fontFamily: '"IBM Plex Mono", Consolas, monospace'
    fontSize: "0.88rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  none: "0"
spacing:
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.25rem"
components:
  button-primary:
    backgroundColor: "{colors.btn}"
    textColor: "{colors.btn-ink}"
    rounded: "{rounded.none}"
    padding: "0.65rem 1rem"
  button-primary-hover:
    backgroundColor: "#3a342b"
    textColor: "{colors.btn-ink}"
    rounded: "{rounded.none}"
    padding: "0.65rem 1rem"
  button-ghost:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.55rem 0.75rem"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "{spacing.lg}"
---

# Design System: Trans Matching

## Overview

**Creative North Star: "The Shared Ledger"**

Trans Matching shares the visual language of [Statements Matcher](https://statements-matcher.onrender.com/): warm paper cream, ink-black actions, square panels, IBM Plex. The dashboard remains an Operate surface (sidebar + live/report), but materials, type, and chrome match the sibling reconciliation tool so accountants move between products without a theme switch.

Surfaces are flat: cream page with soft radial accents, cream-white panels, hairline warm borders. Primary actions are solid ink. Semantic green/amber mark match outcomes; no blue accent.

**Key Characteristics:**

- Warm light theme (`#f3efe6` page, `#fffdf8` panels) with dual radial wash
- Ink (`#1c1a16`) as the only interactive primary — buttons, active filters, progress fill
- Zero border-radius; square corners throughout
- IBM Plex Sans + IBM Plex Mono
- Flat borders (`#c9c0b0`); no drop shadows
- Outcome color via border/text, not thick side-tabs

## Colors

Warm paper ledger palette aligned with Statements Matcher.

### Primary

- **Ink** (`#1c1a16`): Primary buttons, active tabs/filters, progress fill, focused borders.
- **Ink on Cream** (`#f3efe6`): Text on primary buttons (`--btn-ink`).

### Neutral

- **Paper** (`#f3efe6`): Page background.
- **Paper Accent** (`#e4ddd0`): Radial washes, progress track, ready hints.
- **Panel** (`#fffdf8`): Cards, tables, form panels.
- **Line** (`#c9c0b0`): Borders and dividers.
- **Muted** (`#5c564c`): Secondary text and labels.

### Semantic

- **Ok** (`#1f6b3a`): Matched / high confidence.
- **Warn** (`#8a3b12`): Ambiguous / stopped.
- **Danger** (`#9b2c2c`): Errors and stop emphasis.

### Named Rules

**The Ink Action Rule.** Primary interactive fills are ink, never a brand blue.

**The Flat Paper Rule.** No shadows; depth comes from paper vs panel and 1px line borders.

## Typography

**Display/Body:** IBM Plex Sans (Segoe UI fallback)  
**Mono:** IBM Plex Mono (Consolas fallback) for IDs, amounts, filter chips

**Character:** Technical but warm — ledger clarity without a dark console vibe.

### Hierarchy

- **Display** (650, 1.35rem, -0.02em): App title.
- **Title** (650, ~1rem): Trace headings, panel titles.
- **Body** (400, 0.9rem): Controls and copy.
- **Mono** (0.88–0.92rem): Run IDs, report filter chips, amounts.

## Layout

Unchanged Operate shell: 320px sidebar + main; stacks below 900px. Visual materials match Statements Matcher; composition stays Trans Matching.

## Elevation & Depth

Flat. Soft radial gradients on the page only. Panels sit via border + fill contrast, not shadow.

## Shapes

**Square everywhere** (`border-radius: 0`) — form panels, buttons, badges, chips, dropzones.

## Components

### Buttons

- **Primary:** Ink fill, cream text, 1px ink border — matches Statements Matcher `Confronta`.
- **Ghost/Export:** Panel fill, ink text, line border; hover darkens border to ink.
- **Danger:** Panel fill, danger text; hover danger border.

### Filters / Chips

- Inactive: panel + line border; semantic text color for ok/warn.
- Active: ink fill + cream text (same as Statements Matcher `.filter.active`).

### Panels / Table

- Panel cream-white, 1px line border, 1rem padding.
- Tables inside bordered wrap; muted header text; mono amounts.

## Do's and Don'ts

### Do:

- **Do** use Statements Matcher tokens (`--bg`, `--ink`, `--panel`, `--line`, `--ok`, `--warn`).
- **Do** keep primary actions ink-on-cream.
- **Do** use IBM Plex Sans / Mono.
- **Do** keep square corners and flat panels.

### Don't:

- **Don't** reintroduce Signal Blue or dark-console surfaces without an explicit redesign.
- **Don't** add soft pill radii or drop shadows.
- **Don't** use thick colored left borders as the primary outcome cue.
