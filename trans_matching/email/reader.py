from __future__ import annotations

import email
import imaplib
from email.header import decode_header
from email.message import Message

from trans_matching.email.config import EmailConfig, get_email_config
from trans_matching.email.models import EmailMessage, EmailSearchQuery


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _extract_body(msg: Message) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(decoded)
            elif content_type == "text/html":
                html_parts.append(decoded)
        return "\n".join(plain_parts), "\n".join(html_parts)

    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        if msg.get_content_type() == "text/html":
            return "", decoded
        return decoded, ""
    return str(payload or ""), ""


def _parse_message(uid: bytes, raw: bytes, *, include_body: bool) -> EmailMessage:
    msg: Message = email.message_from_bytes(raw)
    body, html_body = _extract_body(msg) if include_body else ("", "")
    return EmailMessage(
        uid=uid.decode(),
        subject=_decode_header_value(msg.get("Subject")),
        sender=_decode_header_value(msg.get("From")),
        date=_decode_header_value(msg.get("Date")),
        body=body,
        html_body=html_body,
        message_id=_decode_header_value(msg.get("Message-ID")),
    )


class GmailReader:
    """Client IMAP Gmail riutilizzabile per qualsiasi verificatore di transazioni."""

    def __init__(self, config: EmailConfig | None = None) -> None:
        self._config = config or get_email_config()
        self._mail: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> GmailReader:
        self.connect()
        return self

    def __exit__(self, *_args: object) -> None:
        self.disconnect()

    def connect(self) -> None:
        if self._mail is not None:
            return
        self._mail = imaplib.IMAP4_SSL(self._config.imap_host, self._config.imap_port)
        self._mail.login(self._config.address, self._config.app_password)
        self._mail.select(self._config.mailbox)

    def disconnect(self) -> None:
        if self._mail is not None:
            try:
                self._mail.logout()
            except imaplib.IMAP4.error:
                pass
            self._mail = None

    def search(self, query: EmailSearchQuery) -> list[EmailMessage]:
        if self._mail is None:
            self.connect()

        assert self._mail is not None
        status, data = self._mail.uid("search", None, query.to_imap_criteria())
        if status != "OK" or not data or not data[0]:
            return []

        results: list[EmailMessage] = []
        for uid in data[0].split():
            status, fetched = self._mail.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not fetched or not fetched[0]:
                continue
            raw = fetched[0][1]
            if isinstance(raw, bytes):
                results.append(_parse_message(uid, raw, include_body=query.include_body))
        return results

    def search_by_text(
        self,
        text: str,
        *,
        from_address: str | None = None,
        include_body: bool = True,
    ) -> list[EmailMessage]:
        return self.search(
            EmailSearchQuery(
                from_address=from_address,
                text=text,
                include_body=include_body,
            )
        )

    def search_by_subject(
        self,
        subject: str,
        *,
        from_address: str | None = None,
        include_body: bool = False,
    ) -> list[EmailMessage]:
        return self.search(
            EmailSearchQuery(
                from_address=from_address,
                subject=subject,
                include_body=include_body,
            )
        )
