# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user: an internal accountant or bookkeeper at a single Italian travel agency. They reconcile corporate Amex card charges against SIAP gestionale export rows — a repetitive, high-volume task where missing or wrong links create accounting rework.

## Product Purpose

Trans Matching automates card-to-gestionale reconciliation for travel-agency accounting. The user uploads an Amex statement (PDF) and a SIAP gestionale export, runs matching, and reviews results with live progress and a persisted audit trail per run.

Success means processing large transaction batches faster than manual reconciliation, with enough traceability to trust and correct outcomes before posting.

## Positioning

Speed and scale at reconciliation volume: run hundreds of card transactions in one session, watch progress live, and retain run history and per-transaction outcomes for review. Domain-specific matchers (Expedia email, MSC, Auto Europe, low-cost ticket codes, multi-line sums) exist to improve match quality, but the product promise is throughput with an audit trail — not a generic spreadsheet workflow.

## Operating Context

- Single agency; not multi-tenant.
- Inputs: Amex PDF statements (including scanned/OCR cases) and SIAP gestionale exports.
- External data: Gmail IMAP for Expedia (`EG*TRVL`) and MSC booking emails when those matchers apply.
- Primary interface: web dashboard (`dashboard/`, served by FastAPI in production).
- CLI/batch entry points (`main.py`, `main_agent.py`) remain for automation and development; the dashboard is the operational surface.
- Deploy target: Render (Docker); filesystem is ephemeral unless persistent disk is enabled (`render.yaml`).

## Capabilities and Constraints

**Core workflow**

1. Upload carta + gestionale files.
2. Optionally limit the transaction row range.
3. Start a matching run; stream agent events and results live.
4. Review report table (matches, confidence, alternatives); export when needed.
5. Browse run history and reopen past runs.

**Matching**

- Agent mode (`MATCHER_MODE=agent`): LangChain/OpenAI agent with specialized tools and routing (Expedia, MSC, Auto Europe, document-group sums, generic gestionale).
- Legacy mode: amount-based matching with optional Expedia email verification.
- Parsers: Amex PDF (text + OCR via RapidOCR), gestionale/SIAP export, supplier-specific verifiers.

**Technical constraints**

- Requires `OPENAI_API_KEY` for agent mode.
- Gmail credentials required for Expedia/MSC email enrichment.
- Amex PDF OCR can peak around 1–2 GB RAM; production should not use undersized instances for scanned PDFs (`render.yaml` notes).
- UI and agent prompts are Italian; SIAP field names and agency terminology are part of the domain model.

**Undecided**

- Multi-agency / tenant support: out of scope for now.
- Persistent production storage: disk mount in `render.yaml` is documented but commented; operational choice not fixed in product record.

## Brand Commitments

- Product name: **Trans Matching**.
- Dashboard subtitle (confirmed in UI): *Agente contabile — carta vs gestionale*.
- Interface language: Italian (`lang="it"` on dashboard shell).
- Voice: practical, accounting-focused; errors and controls use clear operational Italian (e.g. run state, upload conflicts).

## Evidence on Hand

- Working parsers and matchers in `trans_matching/` (Amex, gestionale, Expedia, MSC, Auto Europe).
- Test fixtures and tests under `tests/` (e.g. Amex PDF parsing, upload flow, matching heuristics).
- Sample HTML reports (`report_matching.html`, `report_agent_matching.html`) from prior runs.
- No customer testimonials, case studies, pricing pages, or marketing claims in-repo — future persuade surfaces must not fabricate these.

## Product Principles

1. **Throughput with trust** — Optimize for batch size and speed; every run must remain reviewable (live feed, report, run history).
2. **Agency-specific truth** — SIAP identificativi, Italian descriptions, and supplier patterns (Expedia, MSC, low-cost tickets) are first-class, not afterthoughts.
3. **Single-operator clarity** — One agency, one session model; avoid multi-tenant complexity until explicitly required.
4. **Explain before post** — Surface confidence, alternatives, and agent reasoning so the accountant can accept or override before accounting closure.
5. **Operational honesty** — Reflect real constraints (API keys, Gmail, OCR memory, ephemeral deploy storage) in UX and docs, not hidden failure modes.

## Accessibility & Inclusion

No product-specific accessibility standard confirmed. Dashboard uses some `aria-label` attributes on controls; no further requirement established during init.
