import json
from datetime import datetime, date, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import ReportSubmission, User, WorkItem, RoleType, ItemStatus
from app.schemas.schemas import ReportSubmit, ReportOut
from app.auth.auth import get_current_user
from app.ai.claude import score_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/submit", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def submit_report(
    payload: ReportSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get open tasks for context
    open_tasks = db.query(WorkItem).filter(
        WorkItem.assignee_user_id == current_user.id,
        WorkItem.status.notin_(["completed", "cancelled", "archived"]),
    ).all()
    task_titles = [t.title for t in open_tasks]

    # Score with AI
    score, reasoning = await score_report(
        report_text=payload.report_text,
        open_tasks=task_titles,
        user_name=current_user.name,
    )

    submission = ReportSubmission(
        user_id=current_user.id,
        report_text=payload.report_text,
        ai_score=score,
        ai_score_reasoning=reasoning,
        period_start=payload.period_start,
        period_end=payload.period_end,
        source="web",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/my", response_model=List[ReportOut])
def get_my_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(ReportSubmission)
        .filter(ReportSubmission.user_id == current_user.id)
        .order_by(ReportSubmission.submitted_at.desc())
        .limit(50)
        .all()
    )


@router.get("/", response_model=List[ReportOut])
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager, RoleType.section_head):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    query = db.query(ReportSubmission).order_by(ReportSubmission.submitted_at.desc())
    if current_user.role_type == RoleType.section_head:
        report_ids = [u.id for u in db.query(User).filter(User.parent_id == current_user.id).all()]
        query = query.filter(ReportSubmission.user_id.in_(report_ids))

    return query.limit(200).all()
