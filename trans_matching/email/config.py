from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from trans_matching.paths import ROOT

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class EmailConfig:
    address: str
    app_password: str
    imap_host: str
    imap_port: int
    mailbox: str

    @classmethod
    def from_env(cls) -> EmailConfig:
        address = os.getenv("GMAIL_ADDRESS", "").strip()
        app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

        if not address:
            raise ValueError("GMAIL_ADDRESS non configurato in .env")
        if not app_password:
            raise ValueError("GMAIL_APP_PASSWORD non configurato in .env")

        return cls(
            address=address,
            app_password=app_password.replace(" ", ""),
            imap_host=os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com").strip(),
            imap_port=int(os.getenv("GMAIL_IMAP_PORT", "993")),
            mailbox=os.getenv("GMAIL_MAILBOX", "INBOX").strip(),
        )


def get_email_config() -> EmailConfig:
    return EmailConfig.from_env()
