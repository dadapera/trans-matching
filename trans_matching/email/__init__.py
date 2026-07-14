from trans_matching.email.config import EmailConfig, get_email_config
from trans_matching.email.links import build_gmail_message_link, build_gmail_search_link
from trans_matching.email.models import EmailAttachment, EmailMessage, EmailSearchQuery
from trans_matching.email.reader import GmailReader, verify_gmail_connection

__all__ = [
    "EmailConfig",
    "EmailAttachment",
    "EmailMessage",
    "EmailSearchQuery",
    "GmailReader",
    "build_gmail_message_link",
    "build_gmail_search_link",
    "get_email_config",
    "verify_gmail_connection",
]
