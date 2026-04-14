"""Gmail API integration for receiving and sending emails."""
import base64
import json
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _get_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=settings.gmail_refresh_token,
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def get_gmail_service():
    creds = _get_credentials()
    return build("gmail", "v1", credentials=creds)


def fetch_unread_emails(max_results: int = 50) -> list[dict]:
    """Fetch unread inbox emails from the FinAgent inbox.
    Uses is:unread to stay efficient; deduplication by gmail_message_id
    in the processor prevents re-processing.
    """
    try:
        service = get_gmail_service()
        results = service.users().messages().list(
            userId="me",
            q="is:unread in:inbox",
            maxResults=max_results,
        ).execute()

        messages = results.get("messages", [])
        emails = []
        for msg in messages:
            detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full",
            ).execute()
            parsed = _parse_message(detail)
            if parsed:
                emails.append(parsed)
        return emails
    except Exception as e:
        logger.error(f"Gmail fetch error: {e}")
        return []


def mark_as_read(message_id: str):
    try:
        service = get_gmail_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except Exception as e:
        logger.error(f"Gmail mark-read error: {e}")


def _parse_message(message: dict) -> Optional[dict]:
    """Parse a raw Gmail message into a structured dict."""
    try:
        headers = {h["name"].lower(): h["value"] for h in message["payload"].get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        to = headers.get("to", "")
        cc = headers.get("cc", "")
        date_str = headers.get("date", "")

        recipients = []
        for addr in (to + "," + cc).split(","):
            addr = addr.strip()
            if addr:
                recipients.append(addr)

        body = _extract_body(message["payload"])
        has_attachments = _has_attachments(message["payload"])

        return {
            "gmail_message_id": message["id"],
            "thread_id": message.get("threadId", ""),
            "sender_email": _extract_email(sender),
            "sender_name": _extract_name(sender),
            "recipients": recipients,
            "recipients_emails": [_extract_email(r) for r in recipients],
            "subject": subject,
            "body_text": body,
            "has_attachments": has_attachments,
            "received_at": datetime.utcnow(),
        }
    except Exception as e:
        logger.error(f"Message parse error: {e}")
        return None


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if payload.get("mimeType") == "text/html":
        return ""  # Skip HTML; prefer plain text
    for part in payload.get("parts", []):
        body = _extract_body(part)
        if body:
            return body
    return ""


def _has_attachments(payload: dict) -> bool:
    for part in payload.get("parts", []):
        if part.get("filename") and part.get("body", {}).get("attachmentId"):
            return True
        if _has_attachments(part):
            return True
    return False


def _extract_email(address: str) -> str:
    """Extract email from 'Name <email>' format."""
    if "<" in address and ">" in address:
        return address.split("<")[1].rstrip(">").strip().lower()
    return address.strip().lower()


def _extract_name(address: str) -> str:
    if "<" in address:
        return address.split("<")[0].strip().strip('"')
    return address.strip()


async def send_email(to: str, subject: str, body_html: str, cc: Optional[list[str]] = None):
    """Send an email via Gmail API."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)

        msg.attach(MIMEText(body_html, "html", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service = get_gmail_service()
        service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()
        logger.info(f"Email sent to {to}: {subject}")
    except Exception as e:
        logger.error(f"Gmail send error: {e}")
        raise
