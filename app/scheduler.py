"""APScheduler jobs: email polling, deadline reminders, report prompts, weekly digest."""
import logging
from datetime import datetime, timedelta, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import (
    WorkItem, User, ItemStatus, ItemType,
    RoleType, ReportFrequency
)
from app.email.notifications import (
    dispatch_deadline_reminder, dispatch_overdue_alert,
    dispatch_report_prompt, dispatch_weekly_digest,
    dispatch_followup_reminder,
)
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def get_db() -> Session:
    return SessionLocal()


async def job_poll_emails():
    """Poll Gmail for new emails every 5 minutes."""
    from app.email.processor import process_incoming_emails
    db = get_db()
    try:
        await process_incoming_emails(db, settings.gmail_address)
    except Exception as e:
        logger.error(f"Email poll error: {e}")
    finally:
        db.close()


async def job_deadline_reminders():
    """Send 48h and 24h deadline reminders."""
    db = get_db()
    try:
        now = datetime.utcnow()
        tomorrow = (now + timedelta(hours=24)).date()
        day_after = (now + timedelta(hours=48)).date()
        open_statuses = [ItemStatus.open, ItemStatus.in_progress, ItemStatus.planning, ItemStatus.active]

        items_24h = db.query(WorkItem).filter(
            WorkItem.deadline == tomorrow,
            WorkItem.status.in_(open_statuses),
            WorkItem.assignee_user_id.isnot(None),
        ).all()

        items_48h = db.query(WorkItem).filter(
            WorkItem.deadline == day_after,
            WorkItem.status.in_(open_statuses),
            WorkItem.assignee_user_id.isnot(None),
        ).all()

        for item in items_24h:
            assignee = db.query(User).filter(User.id == item.assignee_user_id).first()
            if assignee:
                await dispatch_deadline_reminder(db, item, assignee, 24)

        for item in items_48h:
            assignee = db.query(User).filter(User.id == item.assignee_user_id).first()
            if assignee:
                await dispatch_deadline_reminder(db, item, assignee, 48)
    except Exception as e:
        logger.error(f"Deadline reminders error: {e}")
    finally:
        db.close()


async def job_overdue_alerts():
    """Flag and notify overdue items at 09:00 each day."""
    db = get_db()
    try:
        yesterday = (datetime.utcnow() - timedelta(days=1)).date()
        open_statuses = [ItemStatus.open, ItemStatus.in_progress, ItemStatus.planning, ItemStatus.active]

        overdue_items = db.query(WorkItem).filter(
            WorkItem.deadline <= yesterday,
            WorkItem.status.in_(open_statuses),
            WorkItem.assignee_user_id.isnot(None),
        ).all()

        for item in overdue_items:
            # Update status to overdue if it's a followup
            if item.type == ItemType.followup:
                item.status = ItemStatus.overdue
                db.commit()

            assignee = db.query(User).filter(User.id == item.assignee_user_id).first()
            reporter = db.query(User).filter(User.id == item.reporter_user_id).first() if item.reporter_user_id else None
            if assignee:
                await dispatch_overdue_alert(db, item, assignee, reporter)
    except Exception as e:
        logger.error(f"Overdue alerts error: {e}")
    finally:
        db.close()


async def job_followup_reminders():
    """Send follow-up reminder 24h before expected_by date."""
    db = get_db()
    try:
        tomorrow = (datetime.utcnow() + timedelta(hours=24)).date()
        items = db.query(WorkItem).filter(
            WorkItem.type == ItemType.followup,
            WorkItem.status == ItemStatus.waiting,
            WorkItem.expected_by == tomorrow,
            WorkItem.awaited_from_user_id.isnot(None),
        ).all()

        for item in items:
            awaited_user = db.query(User).filter(User.id == item.awaited_from_user_id).first()
            if awaited_user:
                await dispatch_followup_reminder(db, item, awaited_user)
    except Exception as e:
        logger.error(f"Follow-up reminders error: {e}")
    finally:
        db.close()


async def job_report_prompts():
    """Send report prompts: daily at 16:00 for students, weekly Thursday 14:00 for economists/section heads."""
    db = get_db()
    try:
        now = datetime.utcnow()
        weekday = now.weekday()  # 0=Mon, 3=Thu

        targets = []
        if True:  # daily students
            students = db.query(User).filter(
                User.role_type == RoleType.student,
                User.is_active == True,
            ).all()
            targets.extend(students)

        if weekday == 3:  # Thursday - economists and section heads
            weekly_users = db.query(User).filter(
                User.role_type.in_([RoleType.economist, RoleType.section_head]),
                User.is_active == True,
            ).all()
            targets.extend(weekly_users)

        for user in targets:
            open_tasks = db.query(WorkItem).filter(
                WorkItem.assignee_user_id == user.id,
                WorkItem.status.notin_(["completed", "cancelled", "archived"]),
            ).all()
            await dispatch_report_prompt(db, user, open_tasks)
    except Exception as e:
        logger.error(f"Report prompts error: {e}")
    finally:
        db.close()


async def job_weekly_digest():
    """Generate and send weekly digest to Division Head every Sunday at 08:00."""
    db = get_db()
    try:
        from app.ai.claude import generate_weekly_digest
        division_head = db.query(User).filter(
            User.role_type == RoleType.division_head,
            User.is_active == True,
        ).first()
        if not division_head:
            return

        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)

        completed = db.query(WorkItem).filter(
            WorkItem.status == ItemStatus.completed,
            WorkItem.completed_at >= week_ago,
        ).all()

        overdue = db.query(WorkItem).filter(
            WorkItem.deadline < now.date(),
            WorkItem.status.in_([ItemStatus.open, ItemStatus.in_progress]),
        ).all()

        stats = {
            "total_open": db.query(WorkItem).filter(
                WorkItem.status.in_([ItemStatus.open, ItemStatus.in_progress])
            ).count(),
            "completed_this_week": len(completed),
            "overdue": len(overdue),
            "new_tasks": db.query(WorkItem).filter(WorkItem.created_at >= week_ago).count(),
        }

        digest = await generate_weekly_digest(
            stats=stats,
            completed_items=[{"title": i.title} for i in completed[:10]],
            overdue_items=[
                {"title": i.title, "assignee": i.assignee.name if i.assignee else "N/A"}
                for i in overdue[:10]
            ],
            top_insights=[],
        )

        await dispatch_weekly_digest(db, division_head, digest)
    except Exception as e:
        logger.error(f"Weekly digest error: {e}")
    finally:
        db.close()


def start_scheduler():
    # Poll emails every 5 minutes
    scheduler.add_job(job_poll_emails, "interval", minutes=5, id="poll_emails")
    # Deadline reminders: every hour
    scheduler.add_job(job_deadline_reminders, "interval", hours=1, id="deadline_reminders")
    # Overdue alerts: daily at 09:00
    scheduler.add_job(job_overdue_alerts, CronTrigger(hour=9, minute=0), id="overdue_alerts")
    # Follow-up reminders: every hour
    scheduler.add_job(job_followup_reminders, "interval", hours=1, id="followup_reminders")
    # Report prompts: daily at 16:00 (students daily, economists/section heads on Thursday)
    scheduler.add_job(job_report_prompts, CronTrigger(hour=16, minute=0), id="report_prompts")
    # Weekly digest: Sunday at 08:00
    scheduler.add_job(job_weekly_digest, CronTrigger(day_of_week="sun", hour=8, minute=0), id="weekly_digest")

    scheduler.start()
    logger.info("Scheduler started")
