"""Notification dispatch: build and send outbound emails for all event types."""
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.models.models import (
    WorkItem, User, Notification, NotificationStatus, ItemType, ItemStatus
)
from app.email.gmail import send_email
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _base_url() -> str:
    return settings.app_url


def _item_url(item_id: int) -> str:
    return f"{_base_url()}/#/items/{item_id}"


def _html_wrapper(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="utf-8"><style>
body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; direction: rtl; }}
.card {{ background: white; border-radius: 8px; padding: 24px; max-width: 600px; margin: auto; }}
h2 {{ color: #1a365d; margin-top: 0; }}
.btn {{ display: inline-block; background: #2b6cb0; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 16px; }}
.footer {{ margin-top: 24px; font-size: 12px; color: #888; }}
</style></head>
<body><div class="card">
<h2>FinAgent - {title}</h2>
{body}
<div class="footer">הודעה זו נשלחה אוטומטית על ידי FinAgent | מחלקת המחקר, בנק ישראל</div>
</div></body></html>"""


async def dispatch_task_assigned(db: Session, item: WorkItem, assignee: User):
    subject = f"[FinAgent] משימה חדשה הוקצתה לך: {item.title}"
    body = f"""<p>שלום {assignee.name},</p>
<p>משימה חדשה הוקצתה לך:</p>
<p><strong>{item.title}</strong></p>
{"<p>תיאור: " + (item.description or "") + "</p>" if item.description else ""}
{"<p>תאריך יעד: " + str(item.deadline) + "</p>" if item.deadline else ""}
<a href="{_item_url(item.id)}" class="btn">צפה במשימה</a>"""
    await _send_and_record(db, assignee.email, subject, _html_wrapper("משימה חדשה", body), "task_assigned", item.id)


async def dispatch_deadline_reminder(db: Session, item: WorkItem, assignee: User, hours_until: int):
    label = "מחר" if hours_until <= 24 else "בעוד 48 שעות"
    subject = f"[FinAgent] תזכורת: {item.title} - תאריך יעד {label}"
    body = f"""<p>שלום {assignee.name},</p>
<p>תזכורת: לקראת תאריך היעד של המשימה <strong>{item.title}</strong></p>
<p>תאריך יעד: <strong>{item.deadline}</strong> ({label})</p>
<a href="{_item_url(item.id)}" class="btn">עדכן סטטוס</a>"""
    await _send_and_record(db, assignee.email, subject, _html_wrapper("תזכורת תאריך יעד", body), "deadline_reminder", item.id)


async def dispatch_overdue_alert(db: Session, item: WorkItem, assignee: User, reporter: Optional[User]):
    subject = f"[FinAgent] איחור: {item.title}"
    body = f"""<p>שלום {assignee.name},</p>
<p>המשימה <strong>{item.title}</strong> עברה את תאריך היעד ({item.deadline}) ועדיין פתוחה.</p>
<a href="{_item_url(item.id)}" class="btn">עדכן סטטוס</a>"""
    recipients = [assignee.email]
    await _send_and_record(db, assignee.email, subject, _html_wrapper("משימה באיחור", body), "task_overdue", item.id)
    if reporter and reporter.email != assignee.email:
        await _send_and_record(db, reporter.email, subject, _html_wrapper("משימה באיחור", body), "task_overdue", item.id)


async def dispatch_followup_reminder(db: Session, item: WorkItem, awaited_user: User):
    subject = f"[FinAgent] ממתין לתגובתך: {item.title}"
    body = f"""<p>שלום {awaited_user.name},</p>
<p>ממתינים לתגובתך בנושא: <strong>{item.title}</strong></p>
{"<p>תאריך סיום צפוי: " + str(item.expected_by) + "</p>" if item.expected_by else ""}
<a href="{_item_url(item.id)}" class="btn">צפה בפרטים</a>"""
    await _send_and_record(db, awaited_user.email, subject, _html_wrapper("ממתין לתגובה", body), "followup_reminder", item.id)


async def dispatch_report_prompt(db: Session, user: User, open_tasks: list):
    subject = "[FinAgent] הגש דיווח סטטוס"
    tasks_html = "".join(f"<li>{t.title}</li>" for t in open_tasks)
    body = f"""<p>שלום {user.name},</p>
<p>נא להגיש עדכון סטטוס עבור המשימות הפתוחות שלך:</p>
<ul>{tasks_html}</ul>
<a href="{_base_url()}/#/report" class="btn">הגש דיווח</a>"""
    await _send_and_record(db, user.email, subject, _html_wrapper("הגשת דיווח", body), "report_prompt", None)


async def dispatch_weekly_digest(db: Session, division_head: User, digest_html: str):
    subject = "[FinAgent] סיכום שבועי - מחלקה פיננסית"
    body = f"<p>שלום {division_head.name},</p>{digest_html}"
    await _send_and_record(db, division_head.email, subject, _html_wrapper("סיכום שבועי", body), "weekly_digest", None)


async def _send_and_record(
    db: Session,
    to: str,
    subject: str,
    body_html: str,
    event_type: str,
    item_id: Optional[int],
):
    notif = Notification(
        recipient_email=to,
        subject=subject,
        body_html=body_html,
        event_type=event_type,
        work_item_id=item_id,
        status=NotificationStatus.pending,
    )
    db.add(notif)
    db.flush()

    try:
        await send_email(to=to, subject=subject, body_html=body_html)
        notif.status = NotificationStatus.sent
        notif.sent_at = datetime.utcnow()
    except Exception as e:
        notif.status = NotificationStatus.failed
        notif.error_message = str(e)
        logger.error(f"Notification send failed to {to}: {e}")

    db.commit()
