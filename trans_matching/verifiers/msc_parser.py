from __future__ import annotations

import re

from trans_matching.email.body import extract_email_text

_MSC_BOOKING = re.compile(
    r"(?:booking(?:\s+reference|\s+number|\s+code)?|prenotazione|reservation)\s*[:#]?\s*([A-Z0-9-]{5,})",
    re.IGNORECASE,
)
_MSC_GUEST = re.compile(
    r"(?:passenger|guest|ospite|pax)\s*[:#]?\s*(.+)",
    re.IGNORECASE,
)
_MSC_AMOUNT = re.compile(
    r"(?:total|importo|amount|prezzo)\s*[:#]?\s*([0-9.,]+)",
    re.IGNORECASE,
)


def parse_msc_email(mail_body: str, mail_html: str = "") -> dict[str, str | None]:
    """Parser MSC stub: estrae campi generici finché non avremo formato definitivo."""
    text = extract_email_text(mail_body, mail_html)
    booking = _MSC_BOOKING.search(text)
    guest = _MSC_GUEST.search(text)
    amount = _MSC_AMOUNT.search(text)
    return {
        "booking_ref": booking.group(1).strip() if booking else None,
        "guest": guest.group(1).splitlines()[0].strip() if guest else None,
        "amount": amount.group(1).strip() if amount else None,
        "parser_status": "stub",
        "text_preview": text[:500],
    }
