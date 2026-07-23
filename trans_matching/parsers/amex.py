from __future__ import annotations

import csv
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from trans_matching.models import Transaction
from trans_matching.parsers.common import format_italian_date, parse_italian_amount
from trans_matching.parsers.pdf_text import (
    extract_pdf_lines_ocr,
    extract_pdf_text,
    pdf_has_text_layer,
)

AMEX_CSV_FIELDS = ("Data", "Descrizione", "Importo")

_AMEX_SKIP = re.compile(
    r"^(Saldo|Accrediti|Addebiti|Importo|TOTALE|Pagina|Data Chiusura|"
    r"Data Prossimo|Data operazione|Estratto Conto|AMERICAN|EXPRESS|"
    r"Titolare|Numero di Carta|Servizio Clienti|Totale nuove|"
    r"L'Importo|Contabilizzata|Descrizione dell'operazione|"
    r"ELISABETTA|LE MONDE|VIA DELLA|ITALY|americanexpress|"
    r"Modalita|Tasso di cambio|Eventuali|In caso|Qualora|"
    r"Per eventuali|Operazioni contabilizzate|Data prossima|"
    r"Addebitata|tramite addebiti|AVVISO|Nuovi addebiti|"
    r"Carta xxxx|Company\.|Roma n\.|Imposta di bollo assolta)",
    re.IGNORECASE,
)
_AMEX_DATE = r"\d{2}\.\d{2}\.\d{2,4}"
_AMEX_DATE_TOKEN = re.compile(rf"^{_AMEX_DATE}$")
_AMEX_AMOUNT = re.compile(r"([\d.]+,\d{2})")
_AMEX_AMOUNT_ONLY = re.compile(r"^([\d.]+,\d{2})(?:\s+CR)?$", re.IGNORECASE)
_AMEX_STATEMENT_LINE = re.compile(
    rf"^({_AMEX_DATE})\s+({_AMEX_DATE})\s+(.+?)\s+([\d.]+,\d{{2}})(?:\s+CR)?$"
)
_AMEX_SINGLE_DATE_LINE = re.compile(
    rf"^({_AMEX_DATE})\s+(.+?)\s+([\d.]+,\d{{2}})(?:\s+CR)?$"
)
_CORRUPTED_DATE = re.compile(r"\b(\d)(\d{2}\.\d{2}\.\d{2})\b")
_EG_TRVL = re.compile(r"(EG\*TRVL\d{14})(\d{10})", re.IGNORECASE)
_DETAIL_HINT = re.compile(
    r"^(ITINERARIO|NUM\.?\s*BIGLIETTO|NOME\s*PASSEGGERO|A:|ARRIVO|PARTENZA|"
    r"Vendita|Trasporti|Alberghi|Servizi|Sterline|Dollari|Fiorini|Zloty|RON|"
    r"Tasso di Cambio|UBICAZIONE|RICONSEGNA|DISTANZA)",
    re.IGNORECASE,
)
_PAGE_BREAK = re.compile(
    r"^(AMERICAN|EXPRESS|Estratto Conto|Pagina\s+\d+|Titolare|LE\s*MONDE|"
    r"Data Contabiliz|operazione data|Data del prossimo)",
    re.IGNORECASE,
)


def parse_amex_file(
    path: Path,
    *,
    on_progress=None,
) -> list[Transaction]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return parse_amex_csv(path)
    if suffix == ".pdf":
        return parse_amex_pdf(path, on_progress=on_progress)
    raise ValueError(f"Formato carta non supportato: {path.name}")


def parse_amex_pdf(path: Path, *, on_progress=None) -> list[Transaction]:
    if pdf_has_text_layer(path):
        if on_progress is not None:
            on_progress(0, 1, "Lettura testo PDF carta…")
        lines = extract_pdf_text(path).splitlines()
        if on_progress is not None:
            on_progress(1, 1, "Testo PDF carta estratto")
    else:
        lines = extract_pdf_lines_ocr(path, on_progress=on_progress)
    return parse_amex_pdf_lines(lines, source=str(path))


def parse_amex_pdf_lines(
    lines: list[str],
    *,
    source: str = "amex-pdf",
) -> list[Transaction]:
    """Parse Amex statement lines; merchant + detail rows go into description."""
    coalesced = _coalesce_amex_ocr_lines(lines)
    closing_date = _extract_statement_closing_date(coalesced)
    transactions: list[Transaction] = []

    i = 0
    while i < len(coalesced):
        line = coalesced[i]
        bollo = _extract_bollo_line(line, closing_date=closing_date)
        if bollo:
            transactions.append(
                Transaction(
                    date=bollo.date,
                    description=bollo.description,
                    amount=bollo.amount,
                    source=source,
                    raw=line,
                )
            )
            i += 1
            continue

        header = _extract_amex_statement_line(line)
        if not header:
            i += 1
            continue

        detail_lines: list[str] = []
        j = i + 1
        while j < len(coalesced):
            nxt = coalesced[j]
            if _extract_amex_statement_line(nxt) or _extract_bollo_line(
                nxt, closing_date=closing_date
            ):
                break
            if _PAGE_BREAK.match(nxt) or _AMEX_SKIP.search(nxt):
                break
            if not nxt.strip():
                j += 1
                continue
            detail_lines.append(nxt)
            j += 1

        credit = bool(re.search(r"\sCR$", line, re.IGNORECASE))
        kept_details: list[str] = []
        for detail in detail_lines:
            if detail.strip().upper() == "CR":
                credit = True
                continue
            if detail.upper().endswith(" CR"):
                credit = True
                kept_details.append(detail[: detail.upper().rfind(" CR")].strip())
                continue
            kept_details.append(detail)

        amount = -abs(header.amount) if credit else header.amount
        description = _compose_amex_description(header.description, kept_details)
        transactions.append(
            Transaction(
                date=header.date,
                description=description,
                amount=amount,
                source=source,
                raw=description,
            )
        )
        i = j

    return transactions


def convert_amex_pdf_to_csv(pdf_path: Path) -> Path:
    """OCR/parse Amex PDF and write CSV with columns Data,Descrizione,Importo."""
    csv_path = pdf_path.with_suffix(".csv")
    write_amex_csv(csv_path, parse_amex_pdf(pdf_path))
    return csv_path


def write_amex_csv(path: Path, transactions: list[Transaction]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AMEX_CSV_FIELDS)
        writer.writeheader()
        for txn in transactions:
            writer.writerow(
                {
                    "Data": txn.date,
                    "Descrizione": txn.description,
                    "Importo": _format_amex_csv_amount(txn.amount),
                }
            )


def _extract_statement_closing_date(lines: list[str]) -> str | None:
    """Data Chiusura appears in the statement header as DD.MM.YYYY."""
    for line in lines[:40]:
        match = re.search(
            r"xxxx[-\w]*\s+(\d{2}\.\d{2}\.\d{4})\s+\d{2}\.\d{2}\.\d{4}",
            line,
            re.IGNORECASE,
        )
        if match:
            return format_italian_date(match.group(1))
        match = re.search(r"Data Chiusura.*?(\d{2}\.\d{2}\.\d{4})", line, re.IGNORECASE)
        if match:
            return format_italian_date(match.group(1))
    return None


def _extract_bollo_line(
    line: str,
    *,
    closing_date: str | None = None,
) -> Transaction | None:
    """TOTALE ALTRI ADDEBITI is the stamp duty row on Italian Amex statements."""
    normalized = re.sub(r"\s+", "", line.upper())
    if "TOTALEALTRIADDEBITI" not in normalized:
        return None
    amount_match = _AMEX_AMOUNT.search(line)
    if not amount_match:
        return None
    return Transaction(
        date=closing_date or "",
        description="IMPOSTA DI BOLLO",
        amount=parse_italian_amount(amount_match.group(1)),
        source="amex-pdf",
        raw=line,
    )


def _coalesce_amex_ocr_lines(lines: list[str]) -> list[str]:
    """Merge OCR splits: amount/CR on next line, dates-only headers, broken merchants."""
    cleaned = [_fix_ocr_amex_dates(re.sub(r"\s+", " ", line.strip())) for line in lines]
    cleaned = [line for line in cleaned if line]

    merged: list[str] = []
    i = 0
    while i < len(cleaned):
        line = cleaned[i]
        nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""

        # Dates only on this line, merchant+amount on next.
        if _is_dates_only_line(line) and nxt and not _is_dates_only_line(nxt):
            if _AMEX_AMOUNT.search(nxt) or _looks_like_merchant_fragment(nxt):
                line = f"{line} {nxt}".strip()
                i += 1
                nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""

        # One date + merchant, next line is date + amount (OCR split; dates may be swapped).
        if (
            _count_amex_dates(line) == 1
            and not _AMEX_AMOUNT.search(line)
            and _count_amex_dates(nxt) == 1
            and _AMEX_AMOUNT.search(nxt)
            and not re.search(r"[A-Za-z]", re.sub(_AMEX_DATE, "", _AMEX_AMOUNT.sub("", nxt)))
        ):
            date_a = re.findall(_AMEX_DATE, line)[0]
            date_b = re.findall(_AMEX_DATE, nxt)[0]
            merchant = re.sub(_AMEX_DATE, "", line).strip()
            amount = _AMEX_AMOUNT.findall(nxt)[-1]
            op_date, post_date = sorted(
                (date_a, date_b),
                key=lambda value: datetime.strptime(value, "%d.%m.%y"),
            )
            line = f"{op_date} {post_date} {merchant} {amount}"
            i += 1
            nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""

        # One date + merchant, second date+amount with leftover text on next.
        elif (
            _count_amex_dates(line) == 1
            and not _AMEX_AMOUNT.search(line)
            and _count_amex_dates(nxt) >= 1
            and _AMEX_AMOUNT.search(nxt)
            and not _looks_like_new_transaction(nxt)
        ):
            dates = re.findall(_AMEX_DATE, f"{line} {nxt}")
            rest = _AMEX_AMOUNT_ONLY.sub("", nxt).strip()
            rest = re.sub(_AMEX_DATE, "", rest).strip()
            merchant = re.sub(_AMEX_DATE, "", line).strip()
            amount = _AMEX_AMOUNT.findall(nxt)[-1]
            if len(dates) >= 2:
                line = f"{dates[0]} {dates[1]} {merchant} {rest} {amount}".strip()
            else:
                line = f"{dates[0]} {merchant} {rest} {amount}".strip()
            line = re.sub(r"\s+", " ", line)
            i += 1
            nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""

        # Header without amount, next line is amount-only.
        if (
            _count_amex_dates(line) >= 1
            and not _AMEX_AMOUNT.search(line)
            and _AMEX_AMOUNT_ONLY.match(nxt)
        ):
            line = f"{line} {nxt}".strip()
            i += 1
            nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""

        # Merchant continuation when previous ended with dates only remnant already handled;
        # handle "19.02.26 EG*TRVL..." missing posting date — leave as single-date.
        # Broken EG*TRVL across two lines after a dates-only remnant.
        if (
            _count_amex_dates(line) >= 1
            and not _AMEX_AMOUNT.search(line)
            and nxt
            and _AMEX_AMOUNT.search(nxt)
            and not re.match(_AMEX_DATE, nxt)
            and not _PAGE_BREAK.match(nxt)
        ):
            line = f"{line} {nxt}".strip()
            i += 1
            nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""

        # CR alone on next line after an amount.
        if _AMEX_AMOUNT.search(line) and not re.search(r"\sCR$", line, re.IGNORECASE):
            if nxt.strip().upper() == "CR":
                line = f"{line} CR"
                i += 1

        merged.append(re.sub(r"\s+", " ", line).strip())
        i += 1

    return merged


def _fix_ocr_amex_dates(line: str) -> str:
    """Fix glued OCR dates like 505.03.26 -> 05.03.26, 612.02.26 -> 12.02.26."""
    return _CORRUPTED_DATE.sub(r"\2", line)


def _is_dates_only_line(line: str) -> bool:
    tokens = line.split()
    if not tokens or len(tokens) > 2:
        return False
    return all(_AMEX_DATE_TOKEN.match(token) for token in tokens)


def _count_amex_dates(line: str) -> int:
    return len(re.findall(_AMEX_DATE, line))


def _looks_like_merchant_fragment(line: str) -> bool:
    if _PAGE_BREAK.match(line) or _AMEX_SKIP.search(line) or _DETAIL_HINT.match(line):
        return False
    return bool(re.search(r"[A-Za-z]", line))


def _looks_like_new_transaction(line: str) -> bool:
    if _is_dates_only_line(line):
        return True
    if _count_amex_dates(line) >= 2 and _AMEX_AMOUNT.search(line):
        return True
    if _count_amex_dates(line) >= 1 and _AMEX_AMOUNT.search(line):
        # Single-date txn header
        after = re.sub(_AMEX_DATE, "", line, count=1).strip()
        return bool(after and not _DETAIL_HINT.match(after))
    return False


def _extract_amex_statement_line(line: str) -> Transaction | None:
    line = _fix_ocr_amex_dates(re.sub(r"\s+", " ", line.strip()))
    if not line or _AMEX_SKIP.search(line):
        return None

    parsed = _parse_amex_statement_fields(line)
    if not parsed:
        return None

    operation_date, description, amount_str, credit = parsed
    if _is_summary_description(description):
        return None

    amount = parse_italian_amount(amount_str)
    if credit:
        amount = -abs(amount)

    return Transaction(
        date=format_italian_date(operation_date),
        description=description.strip(),
        amount=amount,
        source="amex-pdf",
        raw=line,
    )


def _parse_amex_statement_fields(
    line: str,
) -> tuple[str, str, str, bool] | None:
    credit = bool(re.search(r"\sCR$", line, re.IGNORECASE))
    amounts = _AMEX_AMOUNT.findall(line)
    if not amounts:
        return None

    # With FX, OCR may show foreign amount then euro; euro is the last ,XX token.
    amount_str = amounts[-1]
    amount_match = list(_AMEX_AMOUNT.finditer(line))[-1]
    head = line[: amount_match.start()].strip()
    if credit:
        head = re.sub(r"\sCR$", "", head, flags=re.IGNORECASE).strip()

    # Drop trailing foreign-looking amount left in head (e.g. "84.47").
    head = re.sub(r"\s+\d+\.\d{2}$", "", head).strip()

    match = _AMEX_STATEMENT_LINE.match(f"{head} {amount_str}" + (" CR" if credit else ""))
    if not match:
        match = _match_concatenated_amex_dates(f"{head} {amount_str}" + (" CR" if credit else ""))
    if match:
        return match.group(1), match.group(3), amount_str, credit

    single = _AMEX_SINGLE_DATE_LINE.match(f"{head} {amount_str}" + (" CR" if credit else ""))
    if single and not _DETAIL_HINT.match(single.group(2)):
        return single.group(1), single.group(2), amount_str, credit

    dates = re.findall(_AMEX_DATE, head)
    if not dates:
        return None

    after_dates = head
    for date in dates[:2]:
        pos = after_dates.find(date)
        if pos == -1:
            return None
        after_dates = after_dates[pos + len(date) :].lstrip()

    description = after_dates.strip()
    if not description:
        return None

    return dates[0], description, amount_str, credit


def _match_concatenated_amex_dates(line: str) -> re.Match[str] | None:
    """Gestisce righe OCR con date fuse, es. 09.02.2610.02.26 DESCR 118,97."""
    compact = line.replace(" ", "")
    prefix_match = re.match(rf"^({_AMEX_DATE})({_AMEX_DATE})(.*)$", compact)
    if not prefix_match:
        return None

    remainder = prefix_match.group(3)
    amount_match = re.search(r"([\d.]+,\d{2})(?:CR)?$", remainder, re.IGNORECASE)
    if not amount_match:
        return None

    description = remainder[: amount_match.start()].strip()
    if not description:
        return None

    normalized = (
        f"{prefix_match.group(1)} {prefix_match.group(2)} "
        f"{description} {amount_match.group(1)}"
    )
    if compact.upper().endswith("CR"):
        normalized += " CR"
    return _AMEX_STATEMENT_LINE.match(normalized)


def _compose_amex_description(merchant: str, details: list[str]) -> str:
    """Merchant first, then OCR detail lines, all under Descrizione."""
    parts = [_normalize_amex_description(merchant), *[detail.strip() for detail in details if detail.strip()]]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _normalize_amex_description(description: str) -> str:
    """Restore EG*TRVL booking / merchant id spacing lost by OCR."""
    text = _EG_TRVL.sub(r"\1 \2", description)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_ocr_description(description: str) -> str:
    return re.sub(r"[^a-z0-9]", "", description.lower())


def _is_summary_description(description: str) -> bool:
    normalized = _normalize_ocr_description(description)
    return any(
        token in normalized
        for token in (
            "saldo",
            "addebitoincc",
            "addebitoinc/c",
            "accreditiregistrati",
            "addebitiregistrati",
            "importodovuto",
            "totalenuoveoperazioni",
            "salvobuonfine",
            "totalealtriaddebiti",
        )
    )


def parse_amex_csv(path: Path) -> list[Transaction]:
    content = path.read_text(encoding="utf-8")
    if _is_amex_website_export(content):
        return _parse_amex_website_csv(path, content)
    return _parse_amex_simple_csv(path)


def _is_amex_website_export(content: str) -> bool:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Data,"):
            continue
        return ',""' in stripped
    return False


def _parse_amex_website_csv(path: Path, content: str) -> list[Transaction]:
    transactions: list[Transaction] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("Data,"):
            continue

        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]

        match = re.search(r',""([^"]+)""$', line)
        if not match:
            continue

        amount = parse_italian_amount(match.group(1))
        rest = line[: match.start()]
        comma = rest.find(",")
        if comma == -1:
            continue

        transactions.append(
            Transaction(
                date=_format_amex_date(rest[:comma]),
                description=rest[comma + 1 :],
                amount=amount,
                source=str(path),
                raw=line,
            )
        )
    return transactions


def _parse_amex_simple_csv(path: Path) -> list[Transaction]:
    """CSV OCR export: Data,Descrizione,Importo (date already DD/MM/YYYY)."""
    transactions: list[Transaction] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            date_raw = (row.get("Data") or "").strip()
            description = (row.get("Descrizione") or "").strip()
            amount_raw = (row.get("Importo") or "").strip()
            if not date_raw or not amount_raw:
                continue
            transactions.append(
                Transaction(
                    date=format_italian_date(date_raw),
                    description=description,
                    amount=parse_italian_amount(amount_raw),
                    source=str(path),
                    raw=description,
                )
            )
    return transactions


def _format_amex_csv_amount(amount: Decimal) -> str:
    negative = amount < 0
    quantized = f"{abs(amount):.2f}"
    whole, frac = quantized.split(".")
    whole = f"{int(whole):,}".replace(",", ".")
    formatted = f"{whole},{frac}"
    return f"-{formatted}" if negative else formatted


def _format_amex_date(value: str) -> str:
    """Amex website exports card dates as month/day/year."""
    cleaned = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return format_italian_date(cleaned)
