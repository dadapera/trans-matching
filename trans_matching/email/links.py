from __future__ import annotations

from urllib.parse import quote


def build_gmail_message_link(message_id: str) -> str:
    """Link diretto a un messaggio Gmail tramite header Message-ID."""
    clean_id = message_id.strip().strip("<>")
    return f"https://mail.google.com/mail/u/0/#search/rfc822msgid%3A{quote(clean_id)}"


def build_gmail_search_link(query: str) -> str:
    """Link a una ricerca Gmail."""
    return f"https://mail.google.com/mail/u/0/#search/{quote(query)}"
