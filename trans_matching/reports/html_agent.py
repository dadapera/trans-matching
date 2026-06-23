from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from trans_matching.matchers.agent_models import AgentMatchResult
from trans_matching.parsers.common import format_italian_date
from trans_matching.reports.html import _base_html, _format_amount, _html_escape
from trans_matching.storage.agent_repository import AgentRunRecord, load_agent_run_for_report


def _confidence_badge(confidence: str) -> str:
    label = confidence.capitalize()
    return (
        f'<span class="llm-confidence llm-confidence-{confidence}">'
        f"Affidabilità: {label}"
        "</span>"
    )


def _agent_detail(result: AgentMatchResult) -> str:
    parts: list[str] = []

    if result.gestionale:
        labels = " + ".join(
            _html_escape(txn.identificativo)
            for txn in result.gestionale
            if txn.identificativo
        )
        if labels:
            parts.append(f'<span class="identificativo">{labels}</span>')
        for txn in result.gestionale:
            parts.append(
                f'<span class="detail">{_html_escape(format_italian_date(txn.date))} — '
                f'{_html_escape(txn.description)} ({_format_amount(txn.amount)})</span>'
            )

    parts.append(_confidence_badge(result.confidence))

    if result.reason:
        parts.append(
            '<span class="llm-reason">'
            f'<span class="llm-reason-label">Motivazione:</span> '
            f'{_html_escape(result.reason)}'
            "</span>"
        )

    if result.alternatives:
        alt_lines = []
        for alt in result.alternatives:
            ids = ", ".join(alt.identificativi) or "—"
            alt_lines.append(
                f"{_html_escape(ids)} ({alt.confidence}): "
                f"{_html_escape(alt.reason or alt.gestionale_preview)}"
            )
        parts.append(
            '<span class="alternatives">'
            '<span class="alternatives-label">In bilico tra:</span> '
            + "<br>".join(alt_lines)
            + "</span>"
        )

    if result.trace_id:
        parts.append(
            f'<span class="trace-link"><a href="#trace-{_html_escape(result.trace_id)}">'
            f"Trace {_html_escape(result.trace_id)}</a></span>"
        )

    return "".join(parts)


def _format_run_subtitle(run: AgentRunRecord) -> str:
    parts = [f"Run agent #{run.id}"]
    if run.openai_model:
        parts.append(f"modello {run.openai_model}")
    if run.log_path:
        parts.append(f"log {Path(run.log_path).name}")
    return " — ".join(parts)


def generate_agent_html_report(
    output_path: Path,
    *,
    run_id: int | None = None,
    results: list[AgentMatchResult] | None = None,
    run: AgentRunRecord | None = None,
) -> None:
    if results is None:
        run, results = load_agent_run_for_report(run_id)
    elif run is None:
        raise ValueError("run è richiesto quando si passano results in memoria")

    matched = sum(1 for result in results if result.matched)
    ambiguous = sum(1 for result in results if not result.matched and result.alternatives)
    unmatched = len(results) - matched

    rows: list[str] = []
    trace_sections: list[str] = []
    for index, result in enumerate(results, start=1):
        if result.matched:
            icon = "✅"
            row_class = "match"
            status_text = "Match"
        elif result.alternatives:
            icon = "⚠️"
            row_class = "ambiguous"
            status_text = "Ambiguo"
        else:
            icon = "❌"
            row_class = "no-match"
            status_text = "Nessun match"

        rows.append(
            f"""<tr class="{row_class}">
  <td>{index}</td>
  <td class="status">{icon}</td>
  <td>{_html_escape(format_italian_date(result.card.date))}</td>
  <td class="description">{_html_escape(result.card.description)}</td>
  <td class="amount">{_format_amount(result.card.amount)}</td>
  <td class="status-text">{status_text}</td>
  <td>{_agent_detail(result)}</td>
</tr>"""
        )
        if result.trace_id:
            trace_sections.append(
                f'<section id="trace-{_html_escape(result.trace_id)}" class="trace-section">'
                f"<h3>Trace {_html_escape(result.trace_id)}</h3>"
                f"<p>Strategia: {_html_escape(result.strategy)} — "
                f"Confidenza: {_html_escape(result.confidence)} — "
                f"Matched: {result.matched}</p>"
                f"<p>{_html_escape(result.reason)}</p>"
                "</section>"
            )

    extra_css = """
    tr.ambiguous { background: #fffbeb; }
    tr.ambiguous .status-text { color: #b45309; }
    .alternatives { display: block; margin-top: 0.35rem; font-size: 0.8rem; color: #92400e; }
    .alternatives-label { font-weight: 600; }
    .trace-link { display: block; margin-top: 0.35rem; font-size: 0.75rem; }
    .trace-section { margin-top: 2rem; padding: 1rem; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; }
    """

    html = _base_html(
        title="Report Matching Agentico",
        subtitle=_format_run_subtitle(run),
        generated_at=run.created_at,
        summary=[
            (len(results), "Transazioni carta", ""),
            (matched, "✅ Match", "matched"),
            (ambiguous, "⚠️ Ambigui", ""),
            (unmatched - ambiguous, "❌ Senza match", "unmatched"),
        ],
        headers=["#", "", "Data", "Descrizione (carta)", "Importo", "Esito", "Dettaglio"],
        rows=rows,
    )
    html = html.replace("</style>", extra_css + "\n  </style>", 1)
    html = html.replace("</body>", f"<div class='traces'>{''.join(trace_sections)}</div></body>", 1)
    output_path.write_text(html, encoding="utf-8")


def format_generated_label(created_at: str) -> str:
    try:
        return datetime.fromisoformat(created_at).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return created_at
