from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.models import WorkItem, User, ReportSubmission, RoleType, ItemStatus
from app.schemas.schemas import DashboardStats
from app.auth.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    week_end = now + timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    closed_statuses = [ItemStatus.completed, ItemStatus.closed, ItemStatus.cancelled, ItemStatus.archived]
    open_statuses = [s for s in ItemStatus if s not in closed_statuses]

    base = db.query(WorkItem)
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager):
        base = base.filter(WorkItem.assignee_user_id == current_user.id)

    total_open = base.filter(WorkItem.status.in_(open_statuses)).count()
    due_this_week = base.filter(
        WorkItem.status.in_(open_statuses),
        WorkItem.deadline <= week_end.date(),
        WorkItem.deadline >= now.date(),
    ).count()
    overdue = base.filter(
        WorkItem.status.in_(open_statuses),
        WorkItem.deadline < now.date(),
    ).count()
    completed_this_month = base.filter(
        WorkItem.status == ItemStatus.completed,
        WorkItem.completed_at >= month_start,
    ).count()

    return DashboardStats(
        total_open=total_open,
        due_this_week=due_this_week,
        overdue=overdue,
        completed_this_month=completed_this_month,
    )


@router.get("/activity")
def get_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-person recent activity (last update timestamp) for Division Head view."""
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager):
        return []

    users = db.query(User).filter(User.is_active == True).all()
    result = []
    for user in users:
        last_item = (
            db.query(WorkItem)
            .filter(WorkItem.assignee_user_id == user.id)
            .order_by(WorkItem.updated_at.desc())
            .first()
        )
        result.append({
            "user_id": user.id,
            "name": user.name,
            "role_type": user.role_type,
            "last_activity": last_item.updated_at if last_item else None,
            "open_tasks": db.query(WorkItem).filter(
                WorkItem.assignee_user_id == user.id,
                WorkItem.status.notin_(["completed", "cancelled", "archived"]),
            ).count(),
        })
    return result


@router.get("/followups")
def get_open_followups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All open follow-ups with days since sent (for Division Head / Office Manager)."""
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager):
        return []

    from app.models.models import ItemType
    now = datetime.utcnow()
    items = db.query(WorkItem).filter(
        WorkItem.type == ItemType.followup,
        WorkItem.status == ItemStatus.waiting,
    ).all()

    return [
        {
            "id": i.id,
            "title": i.title,
            "awaited_from_user_id": i.awaited_from_user_id,
            "expected_by": i.expected_by,
            "days_since_created": (now - i.created_at).days,
            "is_overdue": i.expected_by and i.expected_by < now.date(),
        }
        for i in items
    ]


@router.get("/reports")
def get_report_scores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager, RoleType.section_head):
        return []

    query = db.query(ReportSubmission).order_by(ReportSubmission.submitted_at.desc())
    if current_user.role_type == RoleType.section_head:
        report_ids = [u.id for u in db.query(User).filter(User.parent_id == current_user.id).all()]
        query = query.filter(ReportSubmission.user_id.in_(report_ids))

    submissions = query.limit(100).all()
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "user_name": s.user.name if s.user else None,
            "ai_score": s.ai_score,
            "ai_score_reasoning": s.ai_score_reasoning,
            "submitted_at": s.submitted_at,
            "period_start": s.period_start,
            "period_end": s.period_end,
        }
        for s in submissions
    ]
