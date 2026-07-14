from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field
from tqdm import tqdm

from trans_matching.config import get_expedia_llm_batch_size, get_openai_config
from trans_matching.email import EmailMessage, GmailReader
from trans_matching.email.body import extract_email_text
from trans_matching.verifiers.expedia_parser import format_llm_email_text
from trans_matching.llm_usage import record_chat_completion, reset_llm_usage
from trans_matching.models import Transaction
from trans_matching.timing import format_elapsed
from trans_matching.verifiers.expedia_trvl import (
    EXPEDIA_SENDER,
    ExpediaTransaction,
    ExpediaVerificationResult,
    LlmConfidence,
    pick_best_email,
    search_expedia_emails,
)


class ExpediaMatchOutput(BaseModel):
    identificativo: str | None = Field(
        default=None,
        description="Identificativo riga gestionale SIAP, es. '998 26 294'",
    )
    hotel: str | None = Field(default=None, description="Nome hotel estratto dall'email")
    guest: str | None = Field(default=None, description="Nome ospite estratto dall'email")
    affidabilita: Literal["basso", "medio", "alto"] = Field(
        description="Affidabilità del match tra email Expedia e gestionale"
    )
    reason: str = Field(
        description="Molto breve spiegazione del match o della mancata corrispondenza"
    )


class ExpediaBatchMatchItem(ExpediaMatchOutput):
    booking_code: str = Field(description="Codice prenotazione Expedia ricevuto in input")


class ExpediaBatchMatchOutput(BaseModel):
    results: list[ExpediaBatchMatchItem]


_SYSTEM_PROMPT = """Sei un assistente che abbina conferme prenotazione hotel Expedia a righe del gestionale contabile SIAP.

Ricevi:
- dati della transazione carta (codice prenotazione, importo, data)
- info estratte dall'email Expedia (hotel, ospite, data pagamento)
- elenco righe gestionale SIAP (identificativo|data|importo|descrizione)

Trova la riga gestionale che corrisponde alla prenotazione nell'email.
Considera che nomi ospiti e hotel possono essere abbreviati, troncati o in formati diversi
(es. COGNOME/NOME, COGNOME NOME, particelle unite o separate, hotel troncati).
L'indicazione del nome hotel può anche mancare e potrebbe essere sostituita da "EXPEDIA INC.".

Valuta "affidabilita" così:
- "alto": corrispondenza chiara e univoca tra email e gestionale
- "medio": corrispondenza probabile ma con ambiguità o dati parziali
- "basso": corrispondenza incerta, assente o basata su pochi indizi

Il campo "affidabilita" e "reason" sono obbligatori in ogni risposta, sia con match positivo sia con identificativo null.
Se non trovi una corrispondenza affidabile, imposta identificativo a null."""

_SYSTEM_PROMPT_BATCH = """Sei un assistente che abbina conferme prenotazione hotel Expedia a righe del gestionale contabile.

Ricevi più prenotazioni Expedia in un unico messaggio, ciascuna con:
- codice prenotazione, importo e data della transazione carta
- testo scarnificato dell'email Expedia (hotel, ospite, data pagamento) corrispondente
- un elenco condiviso di righe gestionale (identificativo|data|importo|descrizione)

Per OGNI prenotazione, trova la riga gestionale corrispondente.
Considera che nomi ospiti e hotel possono essere abbreviati, troncati o in formati diversi.

Valuta "affidabilita" così:
- "alto": corrispondenza chiara e univoca tra email e gestionale
- "medio": corrispondenza probabile ma con ambiguità o dati parziali
- "basso": corrispondenza incerta, assente o basata su pochi indizi

Includi un elemento in "results" per ogni booking_code ricevuto, nello stesso ordine.
I campi "affidabilita" e "reason" sono obbligatori per ogni elemento, sia con match positivo sia con identificativo null.
Se non trovi una corrispondenza affidabile per una prenotazione, imposta identificativo a null."""


@dataclass(frozen=True)
class _PreparedExpedia:
    expedia: ExpediaTransaction
    emails: list[EmailMessage]
    matched_email: EmailMessage
    email_text: str


def _format_gestionale_rows(transactions: list[Transaction]) -> str:
    return "\n".join(
        f"{txn.identificativo}|{txn.date}|{txn.amount}|{txn.description}"
        for txn in transactions
    )


def _find_by_identificativo(
    transactions: list[Transaction],
    identificativo: str,
) -> Transaction | None:
    target = identificativo.strip().upper()
    for txn in transactions:
        if txn.identificativo.strip().upper() == target:
            return txn
    return None


def _build_result_note(
    gestionale: Transaction | None,
    identificativo: object,
    reason: str,
    *,
    batch: bool,
) -> str:
    prefix = "LLM batch" if batch else "LLM"
    if gestionale:
        note = f"Abbinato a {gestionale.identificativo} ({prefix})"
        if reason:
            note = f"{note}: {reason}"
        return note
    if identificativo:
        note = f"LLM ha suggerito {identificativo} ma non trovato nel gestionale"
        if reason:
            note = f"{note}: {reason}"
        return note
    return reason or f"{prefix}: nessun match gestionale"


def _result_from_llm_item(
    prepared: _PreparedExpedia,
    llm_item: ExpediaMatchOutput,
    gestionale_transactions: list[Transaction],
    *,
    batch: bool,
) -> ExpediaVerificationResult:
    identificativo = llm_item.identificativo
    hotel_name = llm_item.hotel
    guest_name = llm_item.guest
    reason = llm_item.reason.strip()
    confidence: LlmConfidence = llm_item.affidabilita

    gestionale: Transaction | None = None
    if identificativo:
        gestionale = _find_by_identificativo(gestionale_transactions, identificativo)

    return ExpediaVerificationResult(
        expedia=prepared.expedia,
        email_found=True,
        emails=prepared.emails,
        hotel_name=hotel_name,
        guest_name=guest_name,
        gestionale=gestionale,
        matched_email=prepared.matched_email,
        note=_build_result_note(gestionale, identificativo, reason, batch=batch),
        llm_reason=reason or None,
        llm_confidence=confidence,
    )


def _error_result(
    prepared: _PreparedExpedia,
    note: str,
) -> ExpediaVerificationResult:
    return ExpediaVerificationResult(
        expedia=prepared.expedia,
        email_found=True,
        emails=prepared.emails,
        matched_email=prepared.matched_email,
        note=note,
    )


def _no_email_result(expedia: ExpediaTransaction) -> ExpediaVerificationResult:
    return ExpediaVerificationResult(
        expedia=expedia,
        email_found=False,
        emails=[],
        note="Nessuna email trovata con questo codice",
    )


def _prepare_expedia(
    expedia: ExpediaTransaction,
    reader: GmailReader,
    *,
    from_address: str,
) -> _PreparedExpedia | None:
    search_result = search_expedia_emails(
        reader,
        expedia.booking_code,
        from_address=from_address,
        include_body=True,
    )
    emails = search_result.emails
    if not emails:
        return None

    matched_email = pick_best_email(emails, expedia.booking_code)
    email_text = format_llm_email_text(matched_email.body, matched_email.html_body)
    return _PreparedExpedia(
        expedia=expedia,
        emails=emails,
        matched_email=matched_email,
        email_text=email_text,
    )


def _format_batch_user_prompt(
    prepared_items: list[_PreparedExpedia],
    gestionale_text: str,
) -> str:
    sections: list[str] = []
    for index, item in enumerate(prepared_items, start=1):
        txn = item.expedia.transaction
        sections.append(
            f"""### Prenotazione {index}
- booking_code: {item.expedia.booking_code}
- importo: {txn.amount}
- data: {txn.date}

Email Expedia:
{item.email_text}
"""
        )

    return (
        "Abbina ciascuna prenotazione a una riga del gestionale.\n\n"
        + "\n".join(sections)
        + "\nGestionale (identificativo|data|importo|descrizione):\n"
        + gestionale_text
    )


def _call_openai_batch(
    client: OpenAI,
    *,
    model: str,
    prepared_items: list[_PreparedExpedia],
    gestionale_text: str,
) -> list[ExpediaBatchMatchItem]:
    user_prompt = _format_batch_user_prompt(prepared_items, gestionale_text)

    response = client.chat.completions.parse(
        model=model,
        response_format=ExpediaBatchMatchOutput,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT_BATCH},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    record_chat_completion(response, model)

    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Risposta OpenAI non parsabile")
    return parsed.results


def _call_openai_single(
    *,
    client: OpenAI,
    model: str,
    booking_code: str,
    card_amount: object,
    card_date: str,
    email_text: str,
    gestionale_text: str,
) -> ExpediaMatchOutput:
    user_prompt = f"""Transazione carta:
- codice prenotazione: {booking_code}
- importo: {card_amount}
- data: {card_date}

Email Expedia:
{email_text}

Gestionale (identificativo|data|importo|descrizione):
{gestionale_text}
"""

    response = client.chat.completions.parse(
        model=model,
        response_format=ExpediaMatchOutput,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    record_chat_completion(response, model)

    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Risposta OpenAI non parsabile")
    return parsed


def _chunked(items: list[_PreparedExpedia], size: int) -> list[list[_PreparedExpedia]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _process_batch(
    prepared_items: list[_PreparedExpedia],
    gestionale_transactions: list[Transaction],
    *,
    client: OpenAI,
    model: str,
    gestionale_text: str,
) -> list[ExpediaVerificationResult]:
    try:
        llm_results = _call_openai_batch(
            client,
            model=model,
            prepared_items=prepared_items,
            gestionale_text=gestionale_text,
        )
    except Exception as exc:
        note = f"Errore LLM batch: {exc}"
        return [_error_result(item, note) for item in prepared_items]

    by_booking_code = {item.booking_code.strip(): item for item in llm_results}

    results: list[ExpediaVerificationResult] = []
    for prepared in prepared_items:
        llm_item = by_booking_code.get(prepared.expedia.booking_code)
        if not llm_item:
            results.append(
                _error_result(
                    prepared,
                    "LLM batch: nessun risultato per questo booking_code",
                )
            )
            continue
        results.append(
            _result_from_llm_item(
                prepared,
                llm_item,
                gestionale_transactions,
                batch=True,
            )
        )
    return results


def _verify_prepared_single(
    prepared: _PreparedExpedia,
    gestionale_transactions: list[Transaction],
    gestionale_text: str,
    *,
    client: OpenAI,
    model: str,
) -> ExpediaVerificationResult:
    txn = prepared.expedia.transaction
    try:
        llm_result = _call_openai_single(
            client=client,
            model=model,
            booking_code=prepared.expedia.booking_code,
            card_amount=txn.amount,
            card_date=txn.date,
            email_text=prepared.email_text,
            gestionale_text=gestionale_text,
        )
    except Exception as exc:
        return _error_result(prepared, f"Errore LLM: {exc}")

    return _result_from_llm_item(
        prepared,
        llm_result,
        gestionale_transactions,
        batch=False,
    )


def verify_many_with_llm(
    expedia_list: list[ExpediaTransaction],
    reader: GmailReader,
    gestionale_transactions: list[Transaction],
    *,
    from_address: str = EXPEDIA_SENDER,
    batch_size: int | None = None,
) -> list[ExpediaVerificationResult]:
    """Cerca email Expedia e abbina al gestionale tramite LLM, in batch."""
    if not expedia_list:
        return []

    reset_llm_usage()
    size = batch_size or get_expedia_llm_batch_size()
    gestionale_text = _format_gestionale_rows(gestionale_transactions)
    config = get_openai_config()
    client = OpenAI(api_key=config.api_key)
    mode_label = "sequenziale" if size <= 1 else f"batch={size}"
    print(
        f"Verifica Expedia LLM ({mode_label}) — "
        f"modello: {config.model}, {len(expedia_list)} transazioni"
    )

    prepared_items: list[_PreparedExpedia] = []
    results: list[ExpediaVerificationResult] = []

    email_bar = tqdm(expedia_list, desc="Email Expedia", unit="txn")
    for expedia in email_bar:
        email_bar.set_postfix_str(expedia.booking_code)
        prepared = _prepare_expedia(
            expedia,
            reader,
            from_address=from_address,
        )
        if prepared is None:
            results.append(_no_email_result(expedia))
        else:
            prepared_items.append(prepared)

    if size <= 1:
        llm_bar = tqdm(prepared_items, desc="Analisi LLM", unit="txn")
        for prepared in llm_bar:
            started_at = time.perf_counter()
            llm_bar.set_postfix_str(prepared.expedia.booking_code)
            results.append(
                _verify_prepared_single(
                    prepared,
                    gestionale_transactions,
                    gestionale_text,
                    client=client,
                    model=config.model,
                )
            )
            llm_bar.set_postfix_str(
                f"{prepared.expedia.booking_code} ({format_elapsed(time.perf_counter() - started_at)})"
            )
        return results

    batch_bar = tqdm(_chunked(prepared_items, size), desc="LLM batch", unit="batch")
    for batch in batch_bar:
        started_at = time.perf_counter()
        codes = ", ".join(item.expedia.booking_code for item in batch)
        batch_bar.set_postfix_str(codes[:60])
        results.extend(
            _process_batch(
                batch,
                gestionale_transactions,
                client=client,
                model=config.model,
                gestionale_text=gestionale_text,
            )
        )
        batch_bar.set_postfix_str(format_elapsed(time.perf_counter() - started_at))

    return results


def verify_with_llm(
    expedia: ExpediaTransaction,
    reader: GmailReader,
    gestionale_transactions: list[Transaction],
    *,
    from_address: str = EXPEDIA_SENDER,
) -> ExpediaVerificationResult:
    """Cerca email Expedia e abbina al gestionale tramite LLM OpenAI (singola)."""
    prepared = _prepare_expedia(
        expedia,
        reader,
        from_address=from_address,
    )
    if prepared is None:
        return _no_email_result(expedia)

    gestionale_text = _format_gestionale_rows(gestionale_transactions)
    config = get_openai_config()
    client = OpenAI(api_key=config.api_key)
    return _verify_prepared_single(
        prepared,
        gestionale_transactions,
        gestionale_text,
        client=client,
        model=config.model,
    )
