from __future__ import annotations

import re
import unicodedata

from trans_matching.models import Transaction

_HOTEL_STOPWORDS = frozenset(
    {
        "HOTEL",
        "INN",
        "THE",
        "DI",
        "DE",
        "LA",
        "LE",
        "IL",
        "AND",
        "BY",
        "SRL",
        "SPA",
        "INC",
        "EXPEDIA",
        "SUITE",
        "SUITES",
        "RESORT",
        "APARTMENTS",
        "APARTMENT",
    }
)

_NAME_PARTICLES = frozenset({"DI", "DE", "DA", "DEL", "DELLA", "VAN", "DER", "VON", "DU", "LA", "LE"})

_GUEST_SLASH = re.compile(r"([A-Z][A-Z']+)/([A-Z' ]+)\s*$")
_EXPEDIA_PREFIX = re.compile(r"^EXPEDIA INC\.?\s*", re.IGNORECASE)


def normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s'/&-]", " ", ascii_text)
    return re.sub(r"\s+", " ", cleaned.upper().strip())


def _merge_particle_tokens(tokens: list[str]) -> list[str]:
    """Unisce particelle al token successivo: DE + ASCENTIIS -> DEASCENTIIS."""
    merged: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _NAME_PARTICLES and index + 1 < len(tokens):
            merged.append(token + tokens[index + 1])
            index += 2
        else:
            merged.append(token)
            index += 1
    return merged


def normalize_guest_parts(name: str) -> frozenset[str]:
    tokens = [token for token in normalize_text(name).replace("/", " ").split() if len(token) > 1]
    merged = _merge_particle_tokens(tokens)
    return frozenset(part for part in merged if len(part) > 1)


def hotel_tokens(hotel: str) -> list[str]:
    raw = normalize_text(hotel).replace("-", " ").replace("&", " ")
    tokens = [
        token
        for token in raw.split()
        if token not in _HOTEL_STOPWORDS and len(token) > 1
    ]
    return tokens


def split_gestionale_description(description: str) -> tuple[str, str | None]:
    """Separa hotel e ospite dalla descrizione gestionale."""
    norm = normalize_text(description)
    norm = _EXPEDIA_PREFIX.sub("", norm).strip()

    slash_match = _GUEST_SLASH.search(norm)
    if slash_match:
        guest = f"{slash_match.group(1)}/{slash_match.group(2).strip()}"
        hotel_part = norm[: slash_match.start()].strip()
        hotel_part = re.sub(r"^\d+\s+", "", hotel_part)
        return hotel_part, guest

    tokens = norm.split()
    if len(tokens) >= 2:
        guest = " ".join(tokens[-2:])
        hotel_part = " ".join(tokens[:-2]).strip()
        hotel_part = re.sub(r"^\d+\s+", "", hotel_part)
        return hotel_part, guest

    return norm, None


def guest_matches(description: str, guest: str) -> bool:
    """Confronta ospite email con gestionale (COGNOME/NOME, COGNOME NOME, DE/DI composti)."""
    email_parts = normalize_guest_parts(guest)
    if len(email_parts) < 2:
        return False

    _, gestionale_guest = split_gestionale_description(description)
    if gestionale_guest:
        gestionale_parts = normalize_guest_parts(gestionale_guest)
        if gestionale_parts and gestionale_parts == email_parts:
            return True

    description_parts = normalize_guest_parts(description.replace("/", " "))
    return email_parts == description_parts or email_parts <= description_parts


def build_hotel_regex(email_hotel: str) -> re.Pattern[str] | None:
    """Regex parziale dal nome hotel email verso il gestionale troncato."""
    tokens = hotel_tokens(email_hotel)
    if not tokens:
        return None

    if len(tokens) == 1:
        word = tokens[0]
        if len(word) < 4:
            return None
        return re.compile(rf"(?:\b|(?<=[\s-])){re.escape(word[:4])}\w*", re.IGNORECASE)

    # Le prime 2 parole identificano quasi sempre l'hotel nel gestionale.
    # SIAP spesso tronca il secondo token: "Jamnagar" -> "JAMN".
    first, second = tokens[0], tokens[1]
    pattern = rf"{re.escape(first)}(?:\s+|-){re.escape(second[:4])}\w*"

    if len(tokens) >= 3:
        last = tokens[2]
        min_len = max(4, len(last) - 2)
        pattern += rf"(?:[\s-]+{re.escape(last[:min_len])}\w*)?"

    # Suffisso troncato nel gestionale: H, HO, I, AI, SUR, PR, ...
    pattern += r"(?:\s+[A-Z]{1,3})?"
    return re.compile(pattern, re.IGNORECASE)


def hotel_matches(description: str, hotel: str) -> bool:
    pattern = build_hotel_regex(hotel)
    if not pattern:
        return False
    search_text = normalize_text(description).replace("-", " ")
    return bool(pattern.search(search_text))


def find_gestionale_by_hotel_and_guest(
    gestionale_transactions: list[Transaction],
    *,
    hotel: str | None,
    guest: str | None,
    amount: object | None = None,
) -> Transaction | None:
    if not guest:
        return None

    scored: list[tuple[int, int, Transaction]] = []
    for txn in gestionale_transactions:
        if not guest_matches(txn.description, guest):
            continue
        if hotel and not hotel_matches(txn.description, hotel):
            continue

        hotel_rank = 1 if hotel else 0
        amount_rank = 1 if amount is not None and txn.amount == amount else 0
        scored.append((hotel_rank, amount_rank, txn))

    if not scored:
        return None

    scored.sort(key=lambda item: (-item[0], -item[1]))
    return scored[0][2]
