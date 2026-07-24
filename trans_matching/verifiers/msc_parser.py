from __future__ import annotations

import re
from io import BytesIO

from pypdf import PdfReader

from trans_matching.email.body import extract_email_text
from trans_matching.email.models import EmailAttachment

_MSC_SUBJECT_BOOKING = re.compile(
    r"Numero\s+di\s+prenotazione\s+per\s+([A-Z0-9]+)\s+(\d+)",
    re.IGNORECASE,
)
_MSC_PDF_BOOKING = re.compile(r"Numero\s+prenotazione\s*:\s*(\d+)", re.IGNORECASE)
_MSC_PASSENGER = re.compile(
    r"\b([A-ZÀ-Ü' -]{2,}),\s*([A-ZÀ-Ü' -]{2,})\s*\(\s*DOB\s*:",
    re.IGNORECASE,
)
_BOOKING_FILENAME = re.compile(r"numero\s+di\s+prenotazione", re.IGNORECASE)
# ponytail: hard caps for 512MB hosts; raise if plan has more RAM.
_MAX_BOOKING_PDF_BYTES = 600_000
_MAX_BOOKING_PDF_PAGES = 2


def parse_msc_email(
    mail_body: str,
    mail_html: str = "",
    *,
    subject: str = "",
    attachments: tuple[EmailAttachment, ...] = (),
) -> dict[str, object]:
    """Estrae dati MSC utili al report, senza matching gestionale."""
    text = extract_email_text(mail_body, mail_html)
    subject_booking = parse_msc_subject(subject)
    pdf_items = [
        item
        for attachment in attachments
        if _is_booking_pdf(attachment)
        if (item := parse_msc_booking_pdf(attachment.data))
    ]
    surnames: set[str] = set()
    for item in pdf_items:
        surnames.update(item["passenger_surnames"])

    return {
        **subject_booking,
        "passenger_surnames": sorted(surnames),
        "booking_pdfs": pdf_items,
        "parser_status": "ok" if surnames else "no_passengers",
        "text_preview": text[:500],
    }


def parse_msc_subject(subject: str) -> dict[str, str | None]:
    match = _MSC_SUBJECT_BOOKING.search(subject)
    if not match:
        return {
            "booking_prefix": None,
            "booking_number": None,
            "booking_code": None,
        }
    prefix = match.group(1).strip().upper()
    number = match.group(2).strip()
    return {
        "booking_prefix": prefix,
        "booking_number": number,
        "booking_code": f"{prefix} {number}",
    }


def parse_msc_booking_pdf(data: bytes) -> dict[str, object] | None:
    if len(data) > _MAX_BOOKING_PDF_BYTES:
        return None
    text = _extract_pdf_text(data)
    if not text:
        return None
    booking = _MSC_PDF_BOOKING.search(text)
    passengers = _MSC_PASSENGER.findall(text)
    surnames = sorted(
        {
            _normalize_name_part(surname)
            for surname, _name in passengers
            if _normalize_name_part(surname)
        }
    )
    if not booking and not surnames:
        return None
    return {
        "booking_number": booking.group(1).strip() if booking else None,
        "passenger_surnames": surnames,
    }


def _is_booking_pdf(attachment: EmailAttachment) -> bool:
    filename = attachment.filename or ""
    is_pdf = (
        attachment.content_type == "application/pdf"
        or filename.lower().endswith(".pdf")
        or attachment.content_type == "application/octet-stream"
    )
    return is_pdf and bool(_BOOKING_FILENAME.search(filename))


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        pages = reader.pages[:_MAX_BOOKING_PDF_PAGES]
        return "\n".join(page.extract_text() or "" for page in pages)
    except Exception:
        return ""


def _normalize_name_part(value: str) -> str:
    return re.sub(r"\s+", " ", value.upper().strip(" ,"))
