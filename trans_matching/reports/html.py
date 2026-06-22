from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from trans_matching.matchers.amount import MatchResult
from trans_matching.parsers.common import format_italian_date
from trans_matching.storage import RunRecord, load_run_for_report


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_amount(amount: Decimal) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _llm_confidence_badge(confidence: str) -> str:
    label = confidence.capitalize()
    return (
        f'<span class="llm-confidence llm-confidence-{confidence}">'
        f"Affidabilità: {label}"
        "</span>"
    )

def _match_detail(result: MatchResult) -> str:
    parts: list[str] = []

    if result.gestionale:
        g = result.gestionale
        if g.identificativo:
            parts.append(f'<span class="identificativo">{_html_escape(g.identificativo)}</span>')
        parts.append(
            f'<span class="detail">{_html_escape(format_italian_date(g.date))} — {_html_escape(g.description)}</span>'
        )

    if result.expedia and result.expedia.llm_confidence:
        parts.append(_llm_confidence_badge(result.expedia.llm_confidence))

    if result.expedia and result.expedia.llm_reason:
        parts.append(
            '<span class="llm-reason">'
            f'<span class="llm-reason-label">Motivazione LLM:</span> '
            f'{_html_escape(result.expedia.llm_reason)}'
            "</span>"
        )
    elif result.expedia and result.expedia.note:
        parts.append(f'<span class="detail">{_html_escape(result.expedia.note)}</span>')

    return "".join(parts)


def _format_run_subtitle(run: RunRecord) -> str:
    parts = [
        f"Run #{run.id}",
        f"matcher {run.expedia_matcher}",
    ]
    if run.openai_model:
        parts.append(f"modello {run.openai_model}")
    if run.llm_batch_size is not None:
        parts.append(f"batch {run.llm_batch_size}")
    return " — ".join(parts)


def generate_html_report(
    output_path: Path,
    *,
    run_id: int | None = None,
    results: list[MatchResult] | None = None,
    run: RunRecord | None = None,
) -> None:
    if results is None:
        run, results = load_run_for_report(run_id)
    elif run is None:
        raise ValueError("run è richiesto quando si passano results in memoria")

    matched = sum(1 for r in results if r.is_matched)
    unmatched = len(results) - matched

    rows = []
    for i, result in enumerate(results, start=1):
        icon = "✅" if result.is_matched else "❌"
        row_class = "match" if result.is_matched else "no-match"
        status_text = "Match" if result.is_matched else "Nessun match"

        rows.append(
            f"""<tr class="{row_class}">
  <td>{i}</td>
  <td class="status">{icon}</td>
  <td>{_html_escape(format_italian_date(result.card.date))}</td>
  <td class="description">{_html_escape(result.card.description)}</td>
  <td class="amount">{_format_amount(result.card.amount)}</td>
  <td class="status-text">{status_text}</td>
  <td>{_match_detail(result)}</td>
</tr>"""
        )

    html = _base_html(
        title="Report Matching Transazioni",
        subtitle=_format_run_subtitle(run),
        generated_at=run.created_at,
        summary=[
            (len(results), "Transazioni carta", ""),
            (matched, "✅ Match", "matched"),
            (unmatched, "❌ Senza match", "unmatched"),
        ],
        headers=["#", "", "Data", "Descrizione (carta)", "Importo", "Esito", "Dettaglio"],
        rows=rows,
    )
    output_path.write_text(html, encoding="utf-8")


def _base_html(
    *,
    title: str,
    subtitle: str,
    generated_at: str,
    summary: list[tuple[int | str, str, str]],
    headers: list[str],
    rows: list[str],
) -> str:
    summary_cards = "".join(
        f"""<div class="summary-card {css}">
  <div class="value">{value}</div>
  <div class="label">{label}</div>
</div>"""
        for value, label, css in summary
    )
    header_cells = "".join(f"<th>{h}</th>" for h in headers)
    try:
        generated_label = datetime.fromisoformat(generated_at).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        generated_label = generated_at

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --green: #16a34a; --red: #dc2626;
      --bg: #f8fafc; --card: #ffffff; --border: #e2e8f0;
      --text: #1e293b; --muted: #64748b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text); padding: 2rem; line-height: 1.5;
    }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
    .meta {{ color: var(--muted); font-size: 0.875rem; margin-bottom: 1.5rem; }}
    .summary {{ display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
    .summary-card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 8px; padding: 1rem 1.5rem; min-width: 140px;
    }}
    .summary-card .value {{ font-size: 1.75rem; font-weight: 700; }}
    .summary-card .label {{ font-size: 0.8rem; color: var(--muted); }}
    .summary-card.matched .value {{ color: var(--green); }}
    .summary-card.unmatched .value {{ color: var(--red); }}
    table {{
      width: 100%; border-collapse: collapse; background: var(--card);
      border: 1px solid var(--border); border-radius: 8px; overflow: hidden; font-size: 0.875rem;
    }}
    th {{ background: #f1f5f9; text-align: left; padding: 0.75rem 1rem; font-weight: 600; border-bottom: 1px solid var(--border); }}
    td {{ padding: 0.6rem 1rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
    tr:last-child td {{ border-bottom: none; }}
    tr.match {{ background: #f0fdf4; }}
    tr.no-match {{ background: #fef2f2; }}
    .status {{ font-size: 1.25rem; text-align: center; width: 3rem; }}
    .amount {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .description {{ max-width: 280px; word-break: break-word; }}
    .identificativo {{ font-weight: 600; display: block; }}
    .detail {{ color: var(--muted); font-size: 0.8rem; display: block; }}
    .llm-reason {{
      color: #475569; font-size: 0.8rem; display: block; margin-top: 0.35rem;
      padding: 0.35rem 0.5rem; background: #f1f5f9; border-radius: 4px;
    }}
    .llm-reason-label {{ font-weight: 600; color: #334155; }}
    .llm-confidence {{
      display: inline-block; font-size: 0.75rem; font-weight: 700;
      padding: 0.15rem 0.45rem; border-radius: 4px; margin-top: 0.35rem;
      text-transform: uppercase; letter-spacing: 0.02em;
    }}
    .llm-confidence-alto {{ background: #dcfce7; color: #166534; }}
    .llm-confidence-medio {{ background: #fef9c3; color: #854d0e; }}
    .llm-confidence-basso {{ background: #fee2e2; color: #991b1b; }}
    .status-text {{ font-weight: 600; }}
    tr.match .status-text {{ color: var(--green); }}
    tr.no-match .status-text {{ color: var(--red); }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">Generato il {generated_label} — {subtitle}</p>
  <div class="summary">{summary_cards}</div>
  <table>
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</body>
</html>"""
