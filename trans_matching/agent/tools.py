from __future__ import annotations

import json
import time
from decimal import Decimal

from langchain_core.tools import tool

from trans_matching.agent.context import get_session
from trans_matching.agent.sum_check import find_amount_combinations
from trans_matching.config import get_agent_log_config, get_msc_email_config
from trans_matching.matchers.agent_models import AgentMatchResult, Confidence, MatchAlternative
from trans_matching.models import Transaction
from trans_matching.verifiers.expedia_parser import format_llm_email_text, parse_expedia_email
from trans_matching.verifiers.expedia_trvl import EXPEDIA_SENDER, extract_booking_code, pick_best_email
from trans_matching.verifiers.msc_parser import parse_msc_email


@tool
def search_gestionale(
    text: str = "",
    amount: float | None = None,
    date_window_days: int | None = None,
    limit: int = 20,
) -> str:
    """Cerca righe nel gestionale SIAP per testo, importo approssimato e finestra date."""
    session = get_session()
    started = time.perf_counter()
    window = date_window_days or session.date_window_days
    amount_decimal = Decimal(str(amount)) if amount is not None else session.card.amount
    rows = session.pool.search(
        text=text or session.card.description,
        amount=amount_decimal,
        card_date=session.card.date,
        date_window_days=window,
        limit=limit,
    )
    payload = {
        "count": len(rows),
        "rows": [session.pool.format_row(txn) for txn in rows],
    }
    _log_tool(session, "search_gestionale", payload, started)
    return json.dumps(payload, ensure_ascii=False)


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
        date_window_days=window,
        tolerance_pct=tolerance_pct,
    )
    payload = {"count": len(combos), "combinations": combos}
    _log_tool(session, "check_sum", {"count": len(combos)}, started)
    return json.dumps(payload, ensure_ascii=False)


@tool
def search_expedia(booking_code: str = "") -> str:
    """Cerca email Expedia per codice prenotazione EG*TRVL e estrae hotel/ospite."""
    session = get_session()
    started = time.perf_counter()
    code = booking_code.strip() or extract_booking_code(session.card.description) or ""
    if not code:
        payload = {"error": "Codice prenotazione Expedia non trovato"}
        _log_tool(session, "search_expedia", payload, started)
        return json.dumps(payload, ensure_ascii=False)

    emails = session.reader.search_by_text(code, from_address=EXPEDIA_SENDER, include_body=True)
    session.logger.log(
        "email_search",
        trace_id=session.trace_id,
        provider="expedia",
        query=code,
        results=len(emails),
    )
    if not emails:
        payload = {"booking_code": code, "email_found": False}
        _log_tool(session, "search_expedia", payload, started)
        return json.dumps(payload, ensure_ascii=False)

    matched_email = pick_best_email(emails, code)
    hotel, guest = parse_expedia_email(matched_email.body, matched_email.html_body)
    email_text = format_llm_email_text(matched_email.body, matched_email.html_body)
    log_config = get_agent_log_config()
    gestionale_hits = session.pool.search_by_guest_hotel(
        guest=guest,
        hotel=hotel,
        amount=session.card.amount,
        card_date=session.card.date,
        date_window_days=session.date_window_days,
    )
    payload = {
        "booking_code": code,
        "email_found": True,
        "hotel": hotel,
        "guest": guest,
        "email_text": email_text if log_config.log_email_body else email_text[:300],
        "gestionale_candidates": [
            session.pool.format_row(txn) for txn in gestionale_hits[:10]
        ],
    }
    _log_tool(session, "search_expedia", {"booking_code": code, "candidates": len(gestionale_hits)}, started)
    return json.dumps(payload, ensure_ascii=False)


@tool
def search_msc(payment_date: str = "", amount: float | None = None) -> str:
    """Cerca email MSC intorno alla data pagamento (parser stub, da affinare)."""
    session = get_session()
    started = time.perf_counter()
    config = get_msc_email_config()
    pay_date = payment_date.strip() or session.card.date
    card_amount = amount if amount is not None else float(session.card.amount)

    collected: list[dict] = []
    for from_address in config.from_addresses:
        for keyword in config.keywords:
            query = keyword
            emails = session.reader.search_by_text(query, from_address=from_address, include_body=True)
            session.logger.log(
                "email_search",
                trace_id=session.trace_id,
                provider="msc",
                from_address=from_address,
                keyword=keyword,
                payment_date=pay_date,
                results=len(emails),
            )
            for mail in emails[:5]:
                parsed = parse_msc_email(mail.body, mail.html_body)
                collected.append(
                    {
                        "from": from_address,
                        "subject": mail.subject,
                        "date": mail.date,
                        "parsed": parsed,
                    }
                )

    gestionale_hits = session.pool.search(
        text="MSC",
        amount=Decimal(str(card_amount)),
        card_date=pay_date,
        date_window_days=config.search_days,
        limit=10,
    )
    payload = {
        "parser_status": "stub",
        "payment_date": pay_date,
        "emails_scanned": len(collected),
        "emails": collected[:5],
        "gestionale_candidates": [session.pool.format_row(txn) for txn in gestionale_hits],
        "note": "Parser MSC incompleto: affinare MSC_EMAIL_FROM e campi email quando disponibili.",
    }
    _log_tool(session, "search_msc", {"emails": len(collected), "candidates": len(gestionale_hits)}, started)
    return json.dumps(payload, ensure_ascii=False)


AGENT_TOOLS = [
    search_gestionale,
    compare_amount,
    check_sum,
    search_expedia,
    search_msc,
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
    confidence: Confidence,
    identificativi: list[str],
    alternatives: list[MatchAlternative],
    pool,
    card_row_number: int,
) -> tuple[bool, list[Transaction], Confidence]:
    """Match confermato solo con confidence alto/medio, identificativi risolvibili e senza conflitti."""
    strong_alternatives = [
        alt for alt in alternatives if alt.confidence in ("alto", "medio")
    ]
    if len(strong_alternatives) >= 2:
        return False, [], "basso"

    if confidence not in ("alto", "medio") or not identificativi:
        return False, [], confidence if confidence == "basso" else "basso"

    if pool.has_assignment_conflict(identificativi, card_row_number):
        return False, [], "basso"

    resolved = pool.find_by_identificativi(identificativi)
    if not resolved:
        return False, [], "basso"
    return True, resolved, confidence


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
    matched, gestionale, final_confidence = apply_confidence_gate(
        confidence=confidence,
        identificativi=identificativi,
        alternatives=alternatives,
        pool=pool,
        card_row_number=row_number,
    )
    gate_reason = reason
    if not matched and pool.has_assignment_conflict(identificativi, row_number):
        gate_reason = f"{reason} [Gate: riga già assegnata ad altra transazione]"
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


def preview_for_identificativi(pool, identificativi: list[str]) -> str:
    rows = pool.find_by_identificativi(identificativi)
    if not rows:
        return ", ".join(identificativi)
    return "; ".join(f"{txn.identificativo} {txn.description[:40]}" for txn in rows)
