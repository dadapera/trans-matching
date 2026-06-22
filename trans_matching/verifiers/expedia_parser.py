from __future__ import annotations

import re

from trans_matching.email.body import extract_email_text
from trans_matching.parsers.common import format_italian_date

_PRENOTATA_PER = re.compile(r"Prenotata per:\s*(.+)", re.IGNORECASE)
_SOGGIORNO_TITLE = re.compile(r"(?:Itinerary:\s*)?Soggiorno\s+(.+)", re.IGNORECASE)
_DATA_PAGAMENTO = re.compile(r"Data del pagamento\s*:?\s*(.+)", re.IGNORECASE)


def parse_hotel_and_guest(text: str) -> tuple[str | None, str | None]:
    guest_match = _PRENOTATA_PER.search(text)
    guest = guest_match.group(1).strip() if guest_match else None

    hotel: str | None = None
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() == "panoramica hotel" and index + 1 < len(lines):
            candidate = lines[index + 1].strip()
            if candidate and not candidate.lower().startswith("via "):
                hotel = candidate
                break

    if not hotel:
        title_match = _SOGGIORNO_TITLE.search(text)
        if title_match:
            hotel = title_match.group(1).strip()

    return hotel, guest


def extract_payment_date(text: str) -> str | None:
    match = _DATA_PAGAMENTO.search(text)
    if match:
        value = match.group(1).strip()
        if value:
            return value.splitlines()[0].strip()

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() == "data del pagamento" and index + 1 < len(lines):
            candidate = lines[index + 1].strip()
            if candidate:
                return candidate
    return None


def format_llm_email_text(mail_body: str, mail_html: str = "") -> str:
    """Riduce l'email Expedia ai soli campi utili per il matching LLM."""
    text = extract_email_text(mail_body, mail_html)
    hotel, guest = parse_hotel_and_guest(text)
    payment_date = extract_payment_date(text)

    parts: list[str] = []
    if hotel:
        parts.append(f"Hotel: {hotel}\n")
    if guest:
        parts.append(f"Ospite: {guest}\n")
    if payment_date:
        parts.append(f"Data pagamento: {format_italian_date(payment_date)}\n")

    return " ".join(parts)


def parse_expedia_email(mail_body: str, mail_html: str = "") -> tuple[str | None, str | None]:
    text = extract_email_text(mail_body, mail_html)
    return parse_hotel_and_guest(text)
