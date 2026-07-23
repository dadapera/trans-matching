from __future__ import annotations

import json
import time
from datetime import timedelta
from decimal import Decimal

from langchain_core.tools import tool

from trans_matching.agent.context import get_session
from trans_matching.agent.dates import date_window_bounds
from trans_matching.agent.sum_check import find_amount_combinations, find_document_amount_groups
from trans_matching.config import get_agent_log_config, get_msc_email_config
from trans_matching.matchers.agent_models import AgentMatchResult, Confidence, MatchAlternative
from trans_matching.matchers.gestionale_text import normalize_text
from trans_matching.parsers.gestionale import format_siap_match_label
from trans_matching.models import Transaction
from trans_matching.email.models import EmailSearchQuery
from trans_matching.verifiers.expedia_parser import format_llm_email_text, parse_expedia_email
from trans_matching.verifiers.expedia_trvl import (
    EXPEDIA_SENDER,
    extract_booking_code,
    pick_best_email,
    search_expedia_emails,
)
from trans_matching.verifiers.msc_parser import parse_msc_email

_MSC_EMAIL_WINDOW_DAYS = 7


@tool
def compare_amount(
    candidate_amounts: list[float],
    card_amount: float | None = None,
) -> str:
    """Confronta importo/i candidati con la transazione carta (delta EUR e %)."""
    session = get_session()
    started = time.perf_counter()
    target = Decimal(str(card_amount if card_amount is not None else session.card.amount))
    comparisons: list[dict] = []
    for value in candidate_amounts:
        candidate = Decimal(str(value))
        if target == 0:
            delta_pct = 0.0
        else:
            delta_pct = float((candidate - target) / target * 100)
        delta_eur = candidate - target
        comparisons.append(
            {
                "candidate": str(candidate),
                "delta_eur": str(delta_eur),
                "delta_pct": round(delta_pct, 2),
                "within_5pct": abs(delta_pct) <= 5,
                "within_15pct": abs(delta_pct) <= 15,
                "note": _amount_note(delta_pct),
            }
        )
    payload = {"card_amount": str(target), "comparisons": comparisons}
    _log_tool(session, "compare_amount", payload, started)
    return json.dumps(payload, ensure_ascii=False)


@tool
def check_sum(
    card_amount: float | None = None,
    date_window_days: int | None = None,
    tolerance_pct: float = 15.0,
) -> str:
    """Trova combinazioni di più righe gestionale la cui somma approssima l'importo carta."""
    session = get_session()
    started = time.perf_counter()
    target = Decimal(str(card_amount if card_amount is not None else session.card.amount))
    window = date_window_days or session.date_window_days
    combos = find_amount_combinations(
        session.pool,
        target_amount=target,
        card_date=session.card.date,
        card_description=session.card.description,
        date_window_days=window,
        tolerance_pct=tolerance_pct,
    )
    payload = {"count": len(combos), "combinations": combos}
    _log_tool(session, "check_sum", {"count": len(combos)}, started)
    return json.dumps(payload, ensure_ascii=False)


@tool
def check_document_group_sum(
    card_amount: float | None = None,
    date_window_days: int | None = None,
    tolerance_pct: float = 15.0,
) -> str:
    """Somma righe SIAP con stesso Documento+Codice Cliente e confronta con la carta."""
    session = get_session()
    payload = collect_document_group_context(
        session,
        card_amount=card_amount,
        date_window_days=date_window_days,
        tolerance_pct=tolerance_pct,
    )
    return json.dumps(payload, ensure_ascii=False)


def collect_document_group_context(
    session,
    *,
    card_amount: float | None = None,
    date_window_days: int | None = None,
    tolerance_pct: float = 15.0,
) -> dict:
    started = time.perf_counter()
    target = Decimal(str(card_amount if card_amount is not None else session.card.amount))
    window = date_window_days or session.date_window_days
    groups = find_document_amount_groups(
        session.pool,
        target_amount=target,
        card_date=session.card.date,
        card_description=session.card.description,
        date_window_days=window,
        tolerance_pct=tolerance_pct,
    )
    payload = {"count": len(groups), "groups": groups}
    _log_tool(session, "check_document_group_sum", {"count": len(groups)}, started)
    return payload


def collect_expedia_context(session, booking_code: str = "") -> dict:
    """Raccoglie il contesto Expedia in modo deterministico prima dell'LLM."""
    started = time.perf_counter()
    code = booking_code.strip() or extract_booking_code(session.card.description) or ""
    if not code:
        payload = {
            "status": "no_booking_code",
            "error": "Codice prenotazione Expedia non trovato",
        }
        _log_tool(session, "expedia_context", payload, started)
        return payload

    search_result = search_expedia_emails(
        session.reader,
        code,
        from_address=EXPEDIA_SENDER,
        include_body=True,
    )
    for attempt in search_result.attempts:
        session.logger.log(
            "email_search",
            trace_id=session.trace_id,
            provider="expedia",
            **attempt,
        )
    emails = search_result.emails
    if not emails:
        payload = {
            "status": "no_email",
            "booking_code": code,
            "email_found": False,
            "search_attempts": search_result.attempts,
        }
        _log_tool(session, "expedia_context", payload, started)
        return payload

    matched_email = pick_best_email(emails, code)
    hotel, guest = parse_expedia_email(matched_email.body, matched_email.html_body)
    email_text = format_llm_email_text(matched_email.body, matched_email.html_body)
    log_config = get_agent_log_config()
    expedia_date_window_days = max(session.date_window_days, 30)
    gestionale_hits = session.pool.search_by_guest_hotel(
        guest=guest,
        hotel=hotel,
        amount=session.card.amount,
        card_date=session.card.date,
        date_window_days=expedia_date_window_days,
    )
    candidate_strategy = "guest_hotel"
    if not gestionale_hits and guest and hotel:
        gestionale_hits = session.pool.search_by_guest_hotel(
            guest=guest,
            hotel=None,
            amount=session.card.amount,
            card_date=session.card.date,
            date_window_days=expedia_date_window_days,
        )
        candidate_strategy = "guest_only"
    payload = {
        "status": "candidates_found" if gestionale_hits else "no_candidates",
        "booking_code": code,
        "email_found": True,
        "search_strategy": search_result.strategy,
        "search_attempts": search_result.attempts,
        "hotel": hotel,
        "guest": guest,
        "candidate_strategy": candidate_strategy,
        "date_window_days": expedia_date_window_days,
        "email_text": email_text if log_config.log_email_body else email_text[:300],
        "gestionale_candidates": [
            session.pool.format_row(txn) for txn in gestionale_hits[:10]
        ],
    }
    _log_tool(
        session,
        "expedia_context",
        {
            "booking_code": code,
            "status": payload["status"],
            "candidate_strategy": candidate_strategy,
            "candidates": len(gestionale_hits),
        },
        started,
    )
    return payload


@tool
def search_msc(search_date: str = "") -> str:
    """Cerca tutte le email MSC per mittente nel range ±7 giorni dalla data indicata."""
    session = get_session()
    payload = collect_msc_context(session, search_date=search_date)
    return json.dumps(payload, ensure_ascii=False)


def collect_msc_context(session, search_date: str = "") -> dict:
    """Raccoglie cognomi passeggeri dagli allegati booking MSC.

    Scarica/parsa una email alla volta e scarta allegati subito: evita OOM su 512MB.
    """
    started = time.perf_counter()
    config = get_msc_email_config()
    target_date = search_date.strip() or session.card.date
    window_start, window_end = date_window_bounds(target_date, days=_MSC_EMAIL_WINDOW_DAYS)

    if window_start is None or window_end is None:
        payload = {"error": f"Data ricerca MSC non valida: {target_date!r}"}
        _log_tool(session, "msc_context", payload, started)
        return payload

    surnames: set[str] = set()
    emails_scanned = 0
    stopped_early = False
    for from_address in config.from_addresses:
        query = EmailSearchQuery(
            from_address=from_address,
            since=window_start.date(),
            before=(window_end + timedelta(days=1)).date(),
            include_body=True,
            include_attachments=True,
            max_results=config.max_results,
            max_body_bytes=config.max_body_bytes,
        )

        def _log_uids(count: int, *, _from=from_address) -> None:
            session.logger.log(
                "email_search",
                trace_id=session.trace_id,
                provider="msc",
                from_address=_from,
                search_date=target_date,
                date_from=window_start.date().isoformat(),
                date_to=window_end.date().isoformat(),
                results=count,
            )

        for mail in session.reader.iter_search(query, on_uids=_log_uids):
            emails_scanned += 1
            parsed = parse_msc_email(
                mail.body,
                mail.html_body,
                subject=mail.subject,
                attachments=mail.attachments,
            )
            for surname in parsed.get("passenger_surnames", []):
                if isinstance(surname, str) and surname:
                    surnames.add(surname)
            # Drop heavy fields before next IMAP fetch.
            del mail
            # ponytail: early-stop after first booking PDF with surnames; ceiling =
            # other MSC emails in the same ±7d window are skipped. Re-scan all if needed.
            if surnames:
                stopped_early = True
                break
        if stopped_early:
            break

    sorted_surnames = sorted(surnames)
    payload = {
        "status": "passengers_found" if sorted_surnames else "no_passengers",
        "search_date": target_date,
        "date_window_days": _MSC_EMAIL_WINDOW_DAYS,
        "max_results_per_sender": config.max_results,
        "max_body_bytes": config.max_body_bytes,
        "emails_scanned": emails_scanned,
        "stopped_early": stopped_early,
        "passenger_surnames": sorted_surnames,
    }
    _log_tool(
        session,
        "msc_context",
        {
            "status": payload["status"],
            "emails": emails_scanned,
            "passenger_surnames": sorted_surnames,
            "stopped_early": stopped_early,
        },
        started,
    )
    return payload


AGENT_TOOLS = [
    compare_amount,
    check_document_group_sum,
    check_sum,
]


def _log_tool(session, name: str, summary: dict, started: float) -> None:
    session.logger.log(
        "tool_call",
        trace_id=session.trace_id,
        step=session.next_tool_step(),
        tool=name,
        output_summary=summary,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _amount_note(delta_pct: float) -> str:
    if abs(delta_pct) <= 3:
        return "Scostamento minimo, plausibile arrotondamento"
    if abs(delta_pct) <= 10:
        return "Scostamento moderato, valuta contesto vendita/markup"
    return "Scostamento elevato, verifica alternative o multi-voce"


def apply_confidence_gate(
    *,
    card: Transaction,
    confidence: Confidence,
    identificativi: list[str],
    alternatives: list[MatchAlternative],
    pool,
    card_row_number: int,
) -> tuple[bool, list[Transaction], Confidence, str | None]:
    """Match confermato con confidence alto/medio e identificativi risolvibili."""
    strong_alternatives = [
        alt for alt in alternatives if alt.confidence in ("alto", "medio")
    ]
    if len(strong_alternatives) >= 2:
        return False, [], "basso", "alternative forti multiple"

    if confidence not in ("alto", "medio") or not identificativi:
        return False, [], confidence if confidence == "basso" else "basso", None

    resolved = pool.find_by_identificativi(identificativi)
    if not resolved:
        return False, [], "basso", "identificativi non risolti o ambigui"

    amount_reason = _amount_gate_reason(card, resolved)
    if amount_reason is not None:
        return False, [], "basso", amount_reason

    merchant_reason = _merchant_gate_reason(card, resolved)
    if merchant_reason is not None:
        return False, [], "basso", merchant_reason

    return True, resolved, confidence, None


def build_result_from_output(
    *,
    card: Transaction,
    trace_id: str,
    row_number: int,
    strategy: str,
    identificativi: list[str],
    confidence: Confidence,
    reason: str,
    alternatives: list[MatchAlternative],
    pool,
) -> AgentMatchResult:
    matched, gestionale, final_confidence, gate_block = apply_confidence_gate(
        card=card,
        confidence=confidence,
        identificativi=identificativi,
        alternatives=alternatives,
        pool=pool,
        card_row_number=row_number,
    )
    gate_reason = reason
    if not matched and gate_block:
        gate_reason = f"{reason} [Gate: {gate_block}]"
    elif not matched and confidence in ("alto", "medio"):
        gate_reason = f"{reason} [Gate: match non confermato]"
    elif not matched and confidence == "basso":
        gate_reason = reason or "Confidenza bassa: nessun match confermato"

    return AgentMatchResult(
        card=card,
        matched=matched,
        gestionale=gestionale,
        confidence=final_confidence if not matched else confidence,
        reason=gate_reason,
        alternatives=alternatives,
        strategy=strategy,
        trace_id=trace_id,
        row_number=row_number,
    )


def _amount_gate_reason(card: Transaction, gestionale: list[Transaction]) -> str | None:
    total = sum((txn.amount for txn in gestionale), Decimal("0"))
    if card.amount == 0:
        return None if total == 0 else "importo gestionale diverso da zero"

    if (card.amount > 0 and total <= 0) or (card.amount < 0 and total >= 0):
        return f"segno importo incoerente: carta {card.amount}, gestionale {total}"

    delta_pct = abs(float((total - card.amount) / card.amount * 100))
    if delta_pct > 15:
        return f"scostamento importo {delta_pct:.2f}% oltre soglia 15%"

    return None


_EXPEDIA_INCOMPATIBLE_TOKENS = {
    "TRE",
    "TRENITALIA",
    "RYA",
    "RYANAIR",
    "WIZ",
    "WIZZ",
    "FB",
    "FLIXBUS",
    "PC",
    "PEGASUS",
    "WY",
    "OMAN",
    "EST",
    "ESTA",
}


def _merchant_gate_reason(card: Transaction, gestionale: list[Transaction]) -> str | None:
    card_text = normalize_text(card.description)
    if "EG*TRVL" not in card_text and "EG TRVL" not in card_text:
        return None

    incompatible_rows = [
        txn.identificativo or txn.description
        for txn in gestionale
        if _is_expedia_incompatible_row(txn)
    ]
    if incompatible_rows:
        return "fornitore gestionale incoerente con Expedia: " + ", ".join(incompatible_rows)
    return None


def _is_expedia_incompatible_row(txn: Transaction) -> bool:
    tokens = normalize_text(txn.description).split()
    if not tokens:
        return False
    return tokens[0] in _EXPEDIA_INCOMPATIBLE_TOKENS or any(
        token in _EXPEDIA_INCOMPATIBLE_TOKENS for token in tokens[:3]
    )


def preview_for_identificativi(pool, identificativi: list[str]) -> str:
    cleaned = [value.strip() for value in identificativi if value.strip()]
    if not cleaned:
        return ""
    rows = pool.find_by_identificativi(cleaned)
    if not rows:
        return ", ".join(cleaned)
    return "; ".join(
        f"{format_siap_match_label(txn.identificativo)} · €{txn.amount} {txn.description[:40]}"
        if txn.identificativo
        else f"{txn.date}|€{txn.amount} {txn.description[:40]}"
        for txn in rows
    )


def clean_identificativi(identificativi: list[str]) -> list[str]:
    return [value.strip() for value in identificativi if value.strip()]
