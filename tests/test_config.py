from trans_matching.config import get_msc_email_config
from trans_matching.email.config import EmailConfig


def test_email_config_reads_imap_timeout(monkeypatch) -> None:
    monkeypatch.setenv("GMAIL_ADDRESS", "USER@GMAIL.COM")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcdefghijklmnop")
    monkeypatch.setenv("GMAIL_IMAP_TIMEOUT_SECONDS", "7.5")

    config = EmailConfig.from_env()

    assert config.address == "user@gmail.com"
    assert config.imap_timeout_seconds == 7.5


def test_msc_email_config_limits_results(monkeypatch) -> None:
    monkeypatch.setenv("MSC_EMAIL_FROM", "a@example.com, b@example.com")
    monkeypatch.setenv("MSC_EMAIL_MAX_RESULTS", "500")
    monkeypatch.setenv("MSC_EMAIL_MAX_BODY_BYTES", "2048")

    config = get_msc_email_config()

    assert config.from_addresses == ("a@example.com", "b@example.com")
    assert config.max_results == 100
    assert config.max_body_bytes == 4096
