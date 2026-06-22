from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from trans_matching.config import ExpediaMatcherMode, get_expedia_matcher_mode
from trans_matching.email import EmailMessage, GmailReader
from trans_matching.matchers.amount import MatchResult
from trans_matching.models import Transaction
from tqdm import tqdm

EXPEDIA_SENDER = "noreply@expediataap.it"
EXPEDIA_TRVL_PATTERN = re.compile(r"EG\*TRVL(\d+)", re.IGNORECASE)

LlmConfidence = Literal["basso", "medio", "alto"]


@dataclass(frozen=True)
class ExpediaTransaction:
    transaction: Transaction
    booking_code: str


@dataclass
class ExpediaVerificationResult:
    expedia: ExpediaTransaction
    email_found: bool
    emails: list[EmailMessage]
    hotel_name: str | None = None
    guest_name: str | None = None
    gestionale: Transaction | None = None
    matched_email: EmailMessage | None = None
    note: str = ""
    llm_reason: str | None = None
    llm_confidence: LlmConfidence | None = None


def extract_booking_code(description: str) -> str | None:
    match = EXPEDIA_TRVL_PATTERN.search(description)
    return match.group(1) if match else None


def filter_expedia_transactions(transactions: list[Transaction]) -> list[ExpediaTransaction]:
    results: list[ExpediaTransaction] = []
    for txn in transactions:
        code = extract_booking_code(txn.description)
        if code:
            results.append(ExpediaTransaction(transaction=txn, booking_code=code))
    return results


def pick_best_email(emails: list[EmailMessage], booking_code: str) -> EmailMessage:
    for mail in emails:
        if booking_code in mail.text_content:
            return mail
    return emails[0]


def verify_booking_confirmation(
    expedia: ExpediaTransaction,
    reader: GmailReader,
    gestionale_transactions: list[Transaction],
    *,
    from_address: str = EXPEDIA_SENDER,
    matcher_mode: ExpediaMatcherMode | None = None,
) -> ExpediaVerificationResult:
    """Cerca email Expedia e abbina al gestionale (regex o LLM)."""
    mode = matcher_mode or get_expedia_matcher_mode()
    if mode == ExpediaMatcherMode.LLM:
        from trans_matching.verifiers.expedia_llm import verify_with_llm

        return verify_with_llm(
            expedia,
            reader,
            gestionale_transactions,
            from_address=from_address,
        )

    from trans_matching.verifiers.expedia_regex import verify_with_regex

    return verify_with_regex(
        expedia,
        reader,
        gestionale_transactions,
        from_address=from_address,
    )


def _transaction_key(transaction: Transaction) -> tuple[str, str, object]:
    return (transaction.date, transaction.description, transaction.amount)


def enrich_with_expedia_verification(
    results: list[MatchResult],
    reader: GmailReader,
    gestionale_transactions: list[Transaction],
    *,
    matcher_mode: ExpediaMatcherMode | None = None,
) -> list[MatchResult]:
    """Abbina transazioni EG*TRVL al gestionale tramite email Expedia."""
    mode = matcher_mode or get_expedia_matcher_mode()
    expedia_txns = filter_expedia_transactions([r.card for r in results])
    verified: dict[tuple[str, str, object], ExpediaVerificationResult] = {}

    unique_expedia: list[ExpediaTransaction] = []
    for expedia in expedia_txns:
        key = _transaction_key(expedia.transaction)
        if key not in verified:
            unique_expedia.append(expedia)

    if mode == ExpediaMatcherMode.LLM:
        from trans_matching.verifiers.expedia_llm import verify_many_with_llm

        for result in verify_many_with_llm(
            unique_expedia,
            reader,
            gestionale_transactions,
        ):
            verified[_transaction_key(result.expedia.transaction)] = result
    else:
        regex_bar = tqdm(unique_expedia, desc="Expedia regex", unit="txn")
        for expedia in regex_bar:
            regex_bar.set_postfix_str(expedia.booking_code)
            verified[_transaction_key(expedia.transaction)] = verify_booking_confirmation(
                expedia,
                reader,
                gestionale_transactions,
                matcher_mode=mode,
            )

    enriched: list[MatchResult] = []
    for result in results:
        expedia = verified.get(_transaction_key(result.card))
        gestionale = result.gestionale
        if expedia and expedia.gestionale and not gestionale:
            gestionale = expedia.gestionale
        enriched.append(
            MatchResult(
                card=result.card,
                matched=result.matched or bool(expedia and expedia.gestionale),
                gestionale=gestionale,
                expedia=expedia,
            )
        )
    return enriched
