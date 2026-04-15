"""Email inbox and thread-history routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Email, WorkItem, User, RoleType
from app.schemas.schemas import EmailOut
from app.auth.auth import get_current_user
from app.email.gmail import send_email
from app.config import get_settings

router = APIRouter(prefix="/api/emails", tags=["emails"])


@router.get("/", response_model=List[EmailOut])
def list_emails(
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recent processed emails. Management only."""
    if current_user.role_type not in (
        RoleType.division_head, RoleType.office_manager, RoleType.section_head
    ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return (
        db.query(Email)
        .order_by(Email.received_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/item/{item_id}", response_model=List[EmailOut])
def get_emails_for_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all emails in the thread linked to a work item."""
    item = db.query(WorkItem).filter(WorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Start from the source email to find the thread_id
    if not item.source_email_id:
        return []

    source = db.query(Email).filter(Email.id == item.source_email_id).first()
    if not source:
        return []

    # Return all emails in the same Gmail thread, ordered chronologically
    if source.thread_id:
        emails = (
            db.query(Email)
            .filter(Email.thread_id == source.thread_id)
            .order_by(Email.received_at.asc())
            .all()
        )
    else:
        emails = [source]

    return emails


@router.get("/{email_id}", response_model=EmailOut)
def get_email(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single email by ID."""
    if current_user.role_type not in (
        RoleType.division_head, RoleType.office_manager, RoleType.section_head
    ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.post("/send-test")
async def send_test_email(
    to: str = Query(...),
    cc: Optional[str] = Query(None),
    subject: str = Query(...),
    body: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: send a test email via the FinAgent Gmail account."""
    if current_user.role_type != RoleType.division_head:
        raise HTTPException(status_code=403, detail="Division head only")
    await send_email(
        to=to,
        subject=subject,
        body_html=body,
        cc=[cc] if cc else None,
    )
    return {"status": "sent", "to": to, "subject": subject}
