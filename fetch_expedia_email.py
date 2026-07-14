"""Recupera il riassunto LLM di un'email Expedia per codice prenotazione."""

from __future__ import annotations

import argparse
import re
import sys

from trans_matching.email import GmailReader
from trans_matching.verifiers.expedia_parser import format_llm_email_text
from trans_matching.verifiers.expedia_trvl import (
    EXPEDIA_SENDER,
    extract_booking_code,
    pick_best_email,
    search_expedia_emails,
)

_EXPEDIA_TRVL_ARG = re.compile(r"EG\*TRVL(\d+)", re.IGNORECASE)


def _normalize_booking_id(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("Codice prenotazione vuoto")

    from_trvl = extract_booking_code(value)
    if from_trvl:
        return from_trvl

    match = _EXPEDIA_TRVL_ARG.search(value)
    if match:
        return match.group(1)

    return value


def fetch_clean_email(
    booking_id: str,
    *,
    include_meta: bool = False,
    full_text: bool = False,
) -> str:
    code = _normalize_booking_id(booking_id)

    with GmailReader() as reader:
        search_result = search_expedia_emails(
            reader,
            code,
            from_address=EXPEDIA_SENDER,
            include_body=True,
        )
        emails = search_result.emails

        if not emails:
            raise LookupError(f"Nessuna email trovata per il codice {code}")

        mail = pick_best_email(emails, code)
        if full_text:
            text = mail.text_content
        else:
            text = format_llm_email_text(mail.body, mail.html_body)
            if not text.strip():
                text = mail.text_content

        if include_meta:
            meta = (
                f"From: {mail.sender}\n"
                f"Subject: {mail.subject}\n"
                f"Date: {mail.date}\n"
                f"UID: {mail.uid}\n"
                f"Emails trovate: {len(emails)}\n"
                f"Strategia ricerca: {search_result.strategy}\n"
                f"Tentativi ricerca: {search_result.attempts}\n"
                f"---\n"
            )
            return meta + text

        return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recupera il riassunto LLM di un'email Expedia da Gmail.",
    )
    parser.add_argument(
        "booking_id",
        help="Codice prenotazione Expedia (es. 73443592561624 o EG*TRVL73443592561624)",
    )
    parser.add_argument(
        "-m",
        "--meta",
        action="store_true",
        help="Includi metadati email prima del testo",
    )
    parser.add_argument(
        "-f",
        "--full",
        action="store_true",
        help="Mostra l'intero testo email invece del riassunto LLM",
    )
    args = parser.parse_args(argv)

    try:
        print(
            fetch_clean_email(
                args.booking_id,
                include_meta=args.meta,
                full_text=args.full,
            ),
            end="",
        )
    except (ValueError, LookupError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
