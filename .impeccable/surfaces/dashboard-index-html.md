---
version: 1
slug: "dashboard-index-html"
primary_target: "dashboard/index.html"
related_targets: []
---

# Dashboard — UX polish (production-ready)

**Mode:** Operate  
**Visitor success:** Complete upload → run → review → export without friction or visual noise during long reconciliation sessions.

## Job and audience

Internal accountant at a single Italian travel agency, reconciling Amex vs SIAP in a long desktop session (often 100+ transactions). They alternate between watching live progress and triaging the report. State of mind: focused, skeptical — they need calm clarity, not stimulation.

## Outcome and proof

**Primary task:** Run a batch match and confidently review outcomes before posting to accounting.

**Success looks like:**
- Zero confusion about what to do next at every step (upload, subset, start, monitor, export)
- Report and live feed scannable at volume without horizontal hunting or clipped content
- Mobile/tablet usable for spot-checks (not primary, but not broken)
- All copy Italian; operational tone per PRODUCT.md

**Product truth to preserve:** Throughput with audit trail — live feed + report + run history stay first-class; polish must not hide agent reasoning or confidence signals.

## Selected direction

**Visual authority:** Extend DESIGN.md *Audit Console* with **quieter tweaks** — same tokens and patterns, slightly softer contrast at rest, more consistent spacing rhythm, no new accent or layout paradigm.

**Structural thesis:** Keep **320px sidebar + main** split. Sidebar = session setup and run control; main = observation (live) and adjudication (report). Do not move features between zones.

**Focal moment:** Post-run report triage — filter chips → table row → jump to trace. Polish should make this path faster to scan, not prettier in isolation.

**Implementation consequence:** CSS-first pass in `dashboard/src/App.css` with minimal TSX changes only where structure blocks polish (empty states, tab semantics, aria). No API/backend changes.

## Scope and boundaries

| In scope | Out of scope |
|----------|----------------|
| Layout rhythm, spacing, typography hierarchy | New features (manual override, bulk actions, settings) |
| Empty, loading, error, and disabled states | Backend/API or data model changes |
| Mobile stack behavior below 900px | Sidebar ↔ main IA redesign |
| Focus-visible, aria improvements, touch targets | Light theme or visual rebrand |
| Report table readability + sticky header polish | Trace-card pattern replacement |
| Quieter contrast (borders, muted text, badge tints) | English localization |

**Fidelity:** Production-ready — one build pass should be shippable.

**Anti-goals:** Decorative motion, marketing empty illustrations, modal-heavy flows, density reduction that hurts throughput.

## States and ranges

| State | Current gap | Polish target |
|-------|-------------|---------------|
| First visit (no files) | Hint text only; run history hidden | Guided empty states in sidebar + main that teach the 3-step flow |
| Upload parsing (OCR) | Progress bar exists | Clearer staged messaging; prevent layout shift |
| Run idle / ready | Hint under controls | Stronger ready vs blocked distinction |
| Run active | Status badge + progress | Preserve; ensure stop control always visible on mobile |
| Live feed empty | Single line centered | Structured empty with link to prerequisites |
| Report building | Same copy as empty finished | Distinguish "waiting for results" vs "run complete, zero rows" |
| Report filtered empty | Plain text | Inline recovery (clear filter CTA) |
| Run error / server lost | Error text in controls | Persistent, scannable error panel styling |
| Historical run loaded | Works | Clear "viewing past run" vs "live" indicator in chrome |

**Data ranges:** 0–500+ report rows; 10–50 concurrent trace cards in live feed; run history list 5–20 items.

## Interaction and layout

### Hierarchy (top → bottom)
1. **Header** — product identity + subtitle; optional subtle session status (files loaded, active run)
2. **Sidebar** — Documenti → Subset → Analisi → Run recenti (when present)
3. **Main tabs** — Attività live | Report (count)
4. **Main content** — feed or table

### Responsiveness
- **≥900px:** Fixed sidebar, main scrolls independently
- **<900px:** Stack sidebar above main; sticky run controls or floating progress bar while running; report table horizontal scroll with first columns pinned if feasible without heavy refactor
- Touch: minimum 44px tap targets on primary actions, tabs, filter chips, run history items

### Affordances and feedback
- Add **focus-visible** rings on all interactive elements (buttons, tabs, dropzones, chips, history items) using accent at 2px offset
- Tabs: consider `role="tablist"` / `aria-selected` without changing visual pattern
- Report filter chips: keep toggle behavior; improve active/inactive contrast gently
- Export button: disabled state must explain why (no rows / exporting)
- Transitions stay 150ms; no new page-load animation

### Quieter visual tweaks (within DESIGN.md)
- Slightly lift border contrast hierarchy: page vs panel vs inset (avoid everything same weight)
- Reduce badge/chip saturation at rest; full semantic color on text and left-edge only
- Increase vertical rhythm in sidebar (consistent 1rem gaps; panel titles breathe)
- Trace card shadow: keep but soften slightly if it competes with feed density

## Constraints and open decisions

**Binding:**
- Platform: web (React 18 + Vite + single `App.css`)
- Italian copy only
- DESIGN.md tokens remain source of truth; quiet tweaks update values in CSS vars, not a new world
- No backend changes

**Reuse:** Existing components (`UploadPanel`, `RunControls`, `LiveFeed`, `ReportTable`, `RunHistory`, `ResultSummary`) — polish in place.

**Open (builder may decide within brief):**
- Whether header gets a compact session-status strip vs leaving status in sidebar only
- Whether mobile uses sticky run bar or keeps controls in stacked sidebar
- Exact empty-state copy (must be written in Italian, operational, no fabricated metrics)

## Recommended build command

`/impeccable polish dashboard` (or direct implementation following this brief + `craft-floor.md`)

**Verify:** Desktop + mobile screenshot pass; `detect.mjs` on changed CSS/TSX; manual flow upload → run → filter report → export.
