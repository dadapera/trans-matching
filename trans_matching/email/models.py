from __future__ import annotations

from dataclasses import dataclass

from trans_matching.email.links import build_gmail_message_link, build_gmail_search_link


@dataclass(frozen=True)
class EmailMessage:
    uid: str
    subject: str
    sender: str
    date: str
    body: str = ""
    html_body: str = ""
    message_id: str = ""

    @property
    def text_content(self) -> str:
        from trans_matching.email.body import extract_email_text

        return extract_email_text(self.body, self.html_body)

    def gmail_url(self, *, fallback_query: str | None = None) -> str:
        if self.message_id:
            return build_gmail_message_link(self.message_id)
        if fallback_query:
            return build_gmail_search_link(fallback_query)
        return build_gmail_search_link(f"from:{self.sender} {self.subject}".strip())


@dataclass(frozen=True)
class EmailSearchQuery:
    """Criteri di ricerca IMAP."""

    from_address: str | None = None
    subject: str | None = None
    text: str | None = None
    include_body: bool = False

    def to_imap_criteria(self) -> str:
        criteria: list[str] = []
        if self.from_address:
            criteria.append(f'FROM "{self.from_address}"')
        if self.subject:
            criteria.append(f'SUBJECT "{self.subject}"')
        if self.text:
            criteria.append(f'TEXT "{self.text}"')
        if not criteria:
            raise ValueError("Almeno un criterio di ricerca è richiesto")
        return f"({' '.join(criteria)})" if len(criteria) > 1 else criteria[0]
