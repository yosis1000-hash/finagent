"""Email processing pipeline: ingests raw emails and creates/updates work items."""
import json
import logging
from datetime import datetime, date
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.models import (
    User, WorkItem, Email, AuditLog,
    ItemType, ItemStatus, Priority,
)
from app.ai.claude import extract_tasks_from_email, parse_finagent_command
from app.email.gmail import fetch_unread_emails, mark_as_read
from app.email.notifications import dispatch_task_assigned
from app.mailbox_identity import body_mentions_agent, is_addressed_to_agent, build_mailbox_aliases

logger = logging.getLogger(__name__)


def is_finagent_addressed(email_data: dict, finagent_email: str) -> bool:
    return is_addressed_to_agent(email_data["recipients_emails"], finagent_email)


def resolve_primary_to(db: Session, raw: dict) -> Optional[User]:
    """Return the first TO recipient who is a known active user,
    excluding the FinAgent mailbox itself and the sender."""
    sender = raw.get("sender_email", "").lower()
    finagent_aliases = build_mailbox_aliases()
    for addr in raw.get("recipients_emails", []):
        addr_lower = addr.strip().lower()
        if addr_lower == sender:
            continue
        if addr_lower in finagent_aliases:
            continue
        # strip any dots/plus Gmail normalisation for alias check
        local = addr_lower.split("@")[0]
        if local in finagent_aliases or local.replace(".", "") in finagent_aliases:
            continue
        user = resolve_user(db, addr_lower)
        if user:
            return user
    return None


def resolve_user(db: Session, email_address: str) -> Optional[User]:
    addr = email_address.lower()
    return db.query(User).filter(
        User.is_active == True,
        or_(User.email == addr, User.notification_email == addr),
    ).first()


async def process_incoming_emails(db: Session, finagent_email: str):
    """Main polling function: fetch unread emails, process each one."""
    emails = fetch_unread_emails(max_results=20)
    for raw in emails:
        # Deduplication
        existing = db.query(Email).filter(
            Email.gmail_message_id == raw["gmail_message_id"]
        ).first()
        if existing:
            continue

        await process_single_email(db, raw, finagent_email)
        mark_as_read(raw["gmail_message_id"])


async def process_single_email(db: Session, raw: dict, finagent_email: str):
    """Process a single email: resolve users, detect commands, extract tasks."""
    sender_user = resolve_user(db, raw["sender_email"])
    known_users = [
        {"name": u.name, "email": u.email, "role_type": u.role_type}
        for u in db.query(User).filter(User.is_active == True).all()
    ]

    # Check for @FinAgent command
    body = raw.get("body_text", "")
    command_data = None
    if is_finagent_addressed(raw, finagent_email) or body_mentions_agent(body, finagent_email):
        command_data = await parse_finagent_command(body, known_users)

    # AI extraction (Observation Mode + Command Mode)
    extraction = await extract_tasks_from_email(
        subject=raw.get("subject", ""),
        body=body,
        sender=raw["sender_email"],
        recipients=raw["recipients_emails"],
        known_users=known_users,
    )

    # Store email record
    email_record = Email(
        gmail_message_id=raw["gmail_message_id"],
        thread_id=raw.get("thread_id"),
        sender_email=raw["sender_email"],
        recipients_json=json.dumps(raw["recipients_emails"]),
        subject=raw.get("subject"),
        body_text=body[:10000],  # truncate for storage
        has_attachments=raw.get("has_attachments", False),
        ai_extracted_tasks=json.dumps(extraction),
        received_at=raw.get("received_at", datetime.utcnow()),
        processed_at=datetime.utcnow(),
    )
    db.add(email_record)
    db.flush()

    # Check if this email belongs to an existing thread with a linked item
    existing_thread_item = None
    if raw.get("thread_id"):
        prior_email = (
            db.query(Email)
            .filter(
                Email.thread_id == raw["thread_id"],
                Email.linked_item_id.isnot(None),
                Email.id != email_record.id,
            )
            .order_by(Email.received_at.desc())
            .first()
        )
        if prior_email:
            existing_thread_item = prior_email.linked_item_id
            email_record.linked_item_id = prior_email.linked_item_id
            # Add activity log to the existing item so the reply is tracked
            linked_item = db.query(WorkItem).filter(WorkItem.id == existing_thread_item).first()
            if linked_item:
                db.add(AuditLog(
                    actor_user_id=sender_user.id if sender_user else None,
                    action="email_reply",
                    entity_type="work_item",
                    entity_id=existing_thread_item,
                    work_item_id=existing_thread_item,
                    details=f"תגובה בשרשור מ-{raw['sender_email']}: {raw.get('subject', '')}",
                ))
                linked_item.updated_at = datetime.utcnow()

    # Execute command if present
    created_item = None
    if command_data and command_data.get("command"):
        created_item = await _execute_command(
            db, command_data, email_record, sender_user, known_users, raw
        )

    # Create ONE consolidated item from AI extraction (Observation Mode):
    # only if no explicit command and not a continuation of an existing thread.
    if not command_data or not command_data.get("command"):
        if not existing_thread_item:
            tasks = extraction.get("tasks", [])
            if tasks:
                await _create_consolidated_item(db, tasks, email_record, sender_user, raw)

    db.commit()

    # Send notifications for created items
    if created_item and created_item.assignee_user_id:
        assignee = db.query(User).filter(User.id == created_item.assignee_user_id).first()
        if assignee:
            await dispatch_task_assigned(db, created_item, assignee)


async def _execute_command(
    db: Session,
    command_data: dict,
    email_record: Email,
    sender_user: Optional[User],
    known_users: list[dict],
    raw: dict,
) -> Optional[WorkItem]:
    cmd = command_data.get("command")
    reporter_id = sender_user.id if sender_user else None

    target_user = None
    if command_data.get("target_person"):
        target_user = resolve_user(db, command_data["target_person"])

    def _link(item: WorkItem) -> WorkItem:
        """Flush item to get its id, then backlink the email to it."""
        db.add(item)
        db.flush()
        email_record.linked_item_id = item.id
        return item

    if cmd == "followup":
        # Determine who we're waiting on: use the primary TO recipient,
        # not the Gemini-parsed target_person (which is unreliable for Hebrew names).
        awaited_user = resolve_primary_to(db, raw) or target_user
        return _link(WorkItem(
            type=ItemType.followup,
            title=f"מעקב: {raw.get('subject', 'ללא נושא')}",
            description=email_record.body_text[:500] if email_record.body_text else None,
            status=ItemStatus.waiting,
            reporter_user_id=reporter_id,
            awaited_from_user_id=awaited_user.id if awaited_user else None,
            expected_by=_parse_date(command_data.get("deadline")),
            source_email_id=email_record.id,
        ))

    elif cmd == "create_task":
        return _link(WorkItem(
            type=ItemType.task,
            title=command_data.get("title") or f"משימה: {raw.get('subject', '')}",
            description=email_record.body_text[:500] if email_record.body_text else None,
            status=ItemStatus.open,
            priority=Priority.medium,
            reporter_user_id=reporter_id,
            assignee_user_id=target_user.id if target_user else None,
            deadline=_parse_date(command_data.get("deadline")),
            source_email_id=email_record.id,
        ))

    elif cmd == "create_project":
        return _link(WorkItem(
            type=ItemType.project,
            title=command_data.get("title") or command_data.get("project_name") or f"פרויקט: {raw.get('subject', '')}",
            status=ItemStatus.planning,
            reporter_user_id=reporter_id,
            source_email_id=email_record.id,
        ))

    elif cmd == "reminder":
        return _link(WorkItem(
            type=ItemType.reminder,
            title=command_data.get("message") or f"תזכורת: {raw.get('subject', '')}",
            status=ItemStatus.open,
            reporter_user_id=reporter_id,
            reminder_message=command_data.get("message"),
            reminder_delivery_at=_parse_date_as_datetime(command_data.get("deadline")),
            source_email_id=email_record.id,
        ))

    elif cmd == "complete":
        # Find the most recent open item linked to this thread
        linked = db.query(WorkItem).filter(
            WorkItem.source_email_id == email_record.id,
        ).first()
        if linked:
            linked.status = ItemStatus.completed
            linked.completed_at = datetime.utcnow()
        return linked

    return None


async def _create_consolidated_item(
    db: Session,
    tasks: list[dict],
    email_record: Email,
    sender_user,
    raw: dict,
):
    """Create a single work item from all AI-extracted tasks for one email.
    - 1 task  → create it as-is
    - 2+ tasks → create one project item with the email subject as title
                 and all tasks listed in the description
    """
    if len(tasks) == 1:
        await _create_item_from_extraction(db, tasks[0], email_record, sender_user, [])
        return

    # Multiple tasks → one consolidated project
    subject = raw.get("subject", "ללא נושא")
    task_lines = "\n".join(f"• {t.get('title', '')}" for t in tasks)
    item = WorkItem(
        type=ItemType.project,
        title=subject,
        description=task_lines,
        status=ItemStatus.planning,
        priority=_parse_priority(tasks[0].get("priority")),
        reporter_user_id=sender_user.id if sender_user else None,
        source_email_id=email_record.id,
    )
    db.add(item)
    db.flush()
    if not email_record.linked_item_id:
        email_record.linked_item_id = item.id


async def _create_item_from_extraction(
    db: Session,
    task_data: dict,
    email_record: Email,
    sender_user: Optional[User],
    known_users: list[dict],
):
    """Create a work item from AI-extracted task data."""
    assignee = None
    if task_data.get("assignee_email"):
        assignee = resolve_user(db, task_data["assignee_email"])

    item_type = ItemType.task
    if task_data.get("type") == "followup":
        item_type = ItemType.followup
    elif task_data.get("type") == "reminder":
        item_type = ItemType.reminder

    item = WorkItem(
        type=item_type,
        title=task_data.get("title", "Untitled"),
        description=task_data.get("description"),
        status=ItemStatus.waiting if item_type == ItemType.followup else ItemStatus.open,
        priority=_parse_priority(task_data.get("priority")),
        reporter_user_id=sender_user.id if sender_user else None,
        assignee_user_id=assignee.id if assignee else None,
        deadline=_parse_date(task_data.get("deadline")),
        source_email_id=email_record.id,
    )
    db.add(item)
    db.flush()
    # Backlink: the email knows which item it created
    if not email_record.linked_item_id:
        email_record.linked_item_id = item.id


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    try:
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_date_as_datetime(value) -> Optional[datetime]:
    d = _parse_date(value)
    if d:
        return datetime.combine(d, datetime.min.time())
    return None


def _parse_priority(value: Optional[str]) -> Priority:
    mapping = {
        "critical": Priority.critical,
        "high": Priority.high,
        "medium": Priority.medium,
        "low": Priority.low,
    }
    return mapping.get((value or "").lower(), Priority.medium)
