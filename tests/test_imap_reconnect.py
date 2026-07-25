import imaplib
import ssl
from unittest.mock import MagicMock, patch

import pytest

from trans_matching.email.reader import (
    GmailReader,
    _is_transient_imap_error,
)


@pytest.mark.parametrize(
    "exc",
    [
        imaplib.IMAP4.error("command: UID => socket error: EOF"),
        imaplib.IMAP4.error("socket error: [SSL: BAD_LENGTH]"),
        TimeoutError(),
        OSError("Connection reset by peer"),
        ssl.SSLError("EOF occurred in violation of protocol"),
        BrokenPipeError(),
    ],
)
def test_is_transient_imap_error(exc: BaseException) -> None:
    assert _is_transient_imap_error(exc)


def test_is_transient_imap_error_rejects_auth() -> None:
    exc = imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
    assert not _is_transient_imap_error(exc)


def test_run_imap_retries_on_socket_eof() -> None:
    reader = GmailReader()
    reader._mail = MagicMock()
    calls = 0

    def action(mail: imaplib.IMAP4_SSL) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise imaplib.IMAP4.error("command: UID => socket error: EOF")
        return "ok"

    with patch.object(reader, "connect") as connect, patch.object(reader, "disconnect") as disconnect:
        result = reader._run_imap(action)

    assert result == "ok"
    assert calls == 2
    disconnect.assert_called_once()
    connect.assert_not_called()


def test_run_imap_retries_on_oserror() -> None:
    reader = GmailReader()
    reader._mail = MagicMock()
    calls = 0

    def action(mail: imaplib.IMAP4_SSL) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("timed out")
        return "ok"

    with patch.object(reader, "connect"), patch.object(reader, "disconnect") as disconnect:
        result = reader._run_imap(action)

    assert result == "ok"
    assert calls == 2
    disconnect.assert_called_once()


def test_run_imap_raises_after_second_eof() -> None:
    reader = GmailReader()
    reader._mail = MagicMock()

    def action(mail: imaplib.IMAP4_SSL) -> str:
        raise imaplib.IMAP4.error("command: UID => socket error: EOF")

    with patch.object(reader, "connect"), patch.object(reader, "disconnect"):
        with pytest.raises(imaplib.IMAP4.error, match="socket error: EOF"):
            reader._run_imap(action)
