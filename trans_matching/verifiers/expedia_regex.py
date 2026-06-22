from __future__ import annotations

from trans_matching.email import EmailMessage, GmailReader
from trans_matching.matchers.gestionale_text import find_gestionale_by_hotel_and_guest
from trans_matching.models import Transaction
from trans_matching.verifiers.expedia_parser import parse_expedia_email
from trans_matching.verifiers.expedia_trvl import (
    EXPEDIA_SENDER,
    ExpediaTransaction,
    ExpediaVerificationResult,
    pick_best_email,
)


def verify_with_regex(
    expedia: ExpediaTransaction,
    reader: GmailReader,
    gestionale_transactions: list[Transaction],
    *,
    from_address: str = EXPEDIA_SENDER,
) -> ExpediaVerificationResult:
    """Cerca email Expedia, estrae hotel/ospite con regex e abbina al gestionale."""
    emails = reader.search_by_text(
        expedia.booking_code,
        from_address=from_address,
        include_body=True,
    )

    if not emails:
        return ExpediaVerificationResult(
            expedia=expedia,
            email_found=False,
            emails=[],
            note="Nessuna email trovata con questo codice",
        )

    matched_email = pick_best_email(emails, expedia.booking_code)
    hotel_name, guest_name = parse_expedia_email(
        matched_email.body,
        matched_email.html_body,
    )

    gestionale = find_gestionale_by_hotel_and_guest(
        gestionale_transactions,
        hotel=hotel_name,
        guest=guest_name,
        amount=expedia.transaction.amount,
    )

    if gestionale:
        note = f"Abbinato a {gestionale.identificativo}"
    elif not hotel_name and not guest_name:
        note = "Email trovata ma hotel/ospite non estratti"
    elif not guest_name:
        note = "Email trovata ma ospite non estratto"
    else:
        note = f"Nessun match gestionale per {guest_name}" + (
            f" / {hotel_name}" if hotel_name else ""
        )

    return ExpediaVerificationResult(
        expedia=expedia,
        email_found=True,
        emails=emails,
        hotel_name=hotel_name,
        guest_name=guest_name,
        gestionale=gestionale,
        matched_email=matched_email,
        note=note,
    )
