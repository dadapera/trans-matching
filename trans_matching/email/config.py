from __future__ import annotations

import os
import re
import ssl
from dataclasses import dataclass

from dotenv import load_dotenv

from trans_matching.paths import ROOT

load_dotenv(ROOT / ".env")

_INVISIBLE_CHARS = re.compile(r"[\s\u200b\u200c\u200d\ufeff]+")


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value


def normalize_gmail_address(raw: str) -> str:
    """Normalizza indirizzo Gmail da env (Render spesso incolla virgolette)."""
    return _strip_wrapping_quotes(raw.strip()).lower()


def normalize_gmail_app_password(raw: str) -> str:
    """Normalizza app password: rimuove spazi e caratteri invisibili da copy-paste."""
    value = _strip_wrapping_quotes(raw.strip())
    return _INVISIBLE_CHARS.sub("", value)


@dataclass(frozen=True)
class EmailConfig:
    address: str
    app_password: str
    imap_host: str
    imap_port: int
    mailbox: str

    @classmethod
    def from_env(cls) -> EmailConfig:
        address = normalize_gmail_address(os.getenv("GMAIL_ADDRESS", ""))
        app_password = normalize_gmail_app_password(os.getenv("GMAIL_APP_PASSWORD", ""))

        if not address:
            raise ValueError("GMAIL_ADDRESS non configurato in .env")
        if not app_password:
            raise ValueError("GMAIL_APP_PASSWORD non configurato in .env")
        if len(app_password) != 16:
            raise ValueError(
                "GMAIL_APP_PASSWORD deve essere una App Password Google di 16 caratteri "
                f"(ricevuti {len(app_password)}). Genera una nuova password da "
                "Account Google → Sicurezza → Password per le app."
            )

        imap_port_raw = _strip_wrapping_quotes(os.getenv("GMAIL_IMAP_PORT", "993").strip())
        try:
            imap_port = int(imap_port_raw)
        except ValueError as exc:
            raise ValueError(f"GMAIL_IMAP_PORT non valido: {imap_port_raw!r}") from exc

        return cls(
            address=address,
            app_password=app_password,
            imap_host=_strip_wrapping_quotes(
                os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com").strip()
            ),
            imap_port=imap_port,
            mailbox=_strip_wrapping_quotes(os.getenv("GMAIL_MAILBOX", "INBOX").strip()),
        )


def get_email_config() -> EmailConfig:
    return EmailConfig.from_env()


def get_imap_ssl_context() -> ssl.SSLContext:
    """SSL per IMAP Gmail.

    Default: verifica certificati attiva. Con proxy/antivirus su Windows spesso
    serve GMAIL_CA_BUNDLE (cert root aziendale) o GMAIL_VERIFY_SSL=false.
    Se GMAIL_* non è impostato, riusa OPENAI_CA_BUNDLE / OPENAI_VERIFY_SSL.
    """
    ca_bundle = (
        _strip_wrapping_quotes(os.getenv("GMAIL_CA_BUNDLE", "").strip())
        or _strip_wrapping_quotes(os.getenv("OPENAI_CA_BUNDLE", "").strip())
    )
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)

    raw = _strip_wrapping_quotes(os.getenv("GMAIL_VERIFY_SSL", "").strip()).lower()
    if not raw:
        raw = _strip_wrapping_quotes(os.getenv("OPENAI_VERIFY_SSL", "true").strip()).lower()
    if raw in {"0", "false", "no", "off"}:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()
