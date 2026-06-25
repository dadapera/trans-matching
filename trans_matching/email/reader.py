from __future__ import annotations

import email
import imaplib
import ssl
from email.header import decode_header
from email.message import Message

from trans_matching.email.config import EmailConfig, get_email_config
from trans_matching.email.models import EmailMessage, EmailSearchQuery

_GMAIL_AUTH_HINT = (
    "Verifica su Render/Dashboard: GMAIL_ADDRESS = email completa dell'account Google; "
    "GMAIL_APP_PASSWORD = password per le app di 16 caratteri (non la password Gmail). "
    "Richiede verifica in 2 passaggi attiva, IMAP abilitato in Gmail "
    "(Impostazioni → Inoltro e POP/IMAP), e Protezione avanzata disattivata."
)


def _imap_auth_error_message(exc: BaseException, config: EmailConfig) -> str:
    detail = str(exc).strip() or repr(exc)
    return (
        f"Gmail IMAP rifiuta il login per {config.address}: {detail}. {_GMAIL_AUTH_HINT}"
    )


def _is_auth_failure(exc: BaseException) -> bool:
    text = str(exc).upper()
    return "AUTHENTICATIONFAILED" in text or "INVALID CREDENTIALS" in text


def verify_gmail_connection(config: EmailConfig | None = None) -> None:
    """Verifica login IMAP Gmail prima di avviare l'analisi."""
    cfg = config or get_email_config()
    reader = GmailReader(cfg)
    try:
        reader.connect()
    except imaplib.IMAP4.error as exc:
        raise RuntimeError(_imap_auth_error_message(exc, cfg)) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Impossibile raggiungere {cfg.imap_host}:{cfg.imap_port}: {exc}"
        ) from exc
    finally:
        reader.disconnect()


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
        ssl_context = ssl.create_default_context()
        self._mail = imaplib.IMAP4_SSL(
            self._config.imap_host,
            self._config.imap_port,
            ssl_context=ssl_context,
        )
        try:
            self._mail.login(self._config.address, self._config.app_password)
            status, _ = self._mail.select(self._config.mailbox)
            if status != "OK":
                raise imaplib.IMAP4.error(f"Selezione mailbox {self._config.mailbox!r} fallita")
        except imaplib.IMAP4.error as exc:
            self.disconnect()
            if _is_auth_failure(exc):
                raise RuntimeError(_imap_auth_error_message(exc, self._config)) from exc
            raise

    def disconnect(self) -> None:
        if self._mail is not None:
            try:
                self._mail.logout()
            except imaplib.IMAP4.error:
                pass
            self._mail = None

    def _ensure_connected(self) -> imaplib.IMAP4_SSL:
        if self._mail is None:
            self.connect()
        assert self._mail is not None
        return self._mail

    def _run_imap(self, action):
        try:
            return action(self._ensure_connected())
        except imaplib.IMAP4.error as exc:
            if not _is_auth_failure(exc):
                raise
            self.disconnect()
            try:
                return action(self._ensure_connected())
            except imaplib.IMAP4.error as retry_exc:
                raise RuntimeError(_imap_auth_error_message(retry_exc, self._config)) from retry_exc

    def search(self, query: EmailSearchQuery) -> list[EmailMessage]:
        def _search(mail: imaplib.IMAP4_SSL) -> list[EmailMessage]:
            status, data = mail.uid("search", None, query.to_imap_criteria())
            if status != "OK" or not data or not data[0]:
                return []

            results: list[EmailMessage] = []
            for uid in data[0].split():
                status, fetched = mail.uid("fetch", uid, "(RFC822)")
                if status != "OK" or not fetched or not fetched[0]:
                    continue
                raw = fetched[0][1]
                if isinstance(raw, bytes):
                    results.append(_parse_message(uid, raw, include_body=query.include_body))
            return results

        return self._run_imap(_search)

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
