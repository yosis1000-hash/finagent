from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, RoleType, AuditLog, WorkItem, ItemStatus, Team, TeamMember, Email, ReportSubmission, Notification
from app.org_config import build_default_config, load_org_config, save_org_config
from app.schemas.schemas import UserCreate, UserUpdate, UserOut
from app.auth.auth import get_current_user, hash_password, require_roles

DEFAULT_CONFIG = {
    "org_name": "אגף",
    "role_labels": {
        "division_head": "ראש אגף",
        "department_head": "ראש מחלקה",
        "section_head": "ראש תחום",
        "office_manager": "מנהלת משרד",
        "economist": "כלכלן",
        "student": "סטודנט",
        "advisor": "יועץ",
        "team_lead": "ראש צוות",
        "external": "חיצוני",
    }
}
DEFAULT_CONFIG = build_default_config()

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Division head and office manager see all; section heads see their reports
    if current_user.role_type in (RoleType.division_head, RoleType.office_manager):
        return db.query(User).filter(User.is_active == True).all()
    elif current_user.role_type == RoleType.section_head:
        # Section head + their direct reports
        ids = {current_user.id}
        for u in db.query(User).filter(User.parent_id == current_user.id).all():
            ids.add(u.id)
        return db.query(User).filter(User.id.in_(ids), User.is_active == True).all()
    else:
        return [current_user]


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return load_org_config(db)


@router.put("/config")
def update_config(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head, RoleType.office_manager)),
):
    return save_org_config(db, payload)


@router.get("/org-tree")
def get_org_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the full org hierarchy as a nested structure with task stats."""
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    all_users = db.query(User).filter(User.is_active == True).all()
    closed = [ItemStatus.completed, ItemStatus.closed, ItemStatus.cancelled, ItemStatus.archived]

    # Precompute task stats per user
    def task_stats(user_id: int):
        open_count = db.query(WorkItem).filter(
            WorkItem.assignee_user_id == user_id,
            WorkItem.status.notin_(closed),
        ).count()
        done_count = db.query(WorkItem).filter(
            WorkItem.assignee_user_id == user_id,
            WorkItem.status == ItemStatus.completed,
        ).count()
        return open_count, done_count

    # Precompute team memberships per user
    memberships = db.query(TeamMember).all()
    teams = db.query(Team).filter(Team.is_active == True).all()
    team_map = {t.id: t.name for t in teams}
    user_teams: dict = {}
    for m in memberships:
        user_teams.setdefault(m.user_id, []).append(team_map.get(m.team_id, ""))

    def build_node(user: User):
        children = [u for u in all_users if u.parent_id == user.id]
        open_t, done_t = task_stats(user.id)
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role_type": user.role_type,
            "open_tasks": open_t,
            "done_tasks": done_t,
            "teams": user_teams.get(user.id, []),
            "children": [build_node(c) for c in children],
        }

    roots = [u for u in all_users if u.parent_id is None]
    return [build_node(r) for r in roots]


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head, RoleType.office_manager)),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role_type=payload.role_type,
        parent_id=payload.parent_id,
        report_frequency=payload.report_frequency,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _log(db, current_user.id, "create", "user", user.id, f"Created user {user.email}")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only division_head/office_manager can edit others; users can edit themselves (limited)
    if current_user.id != user_id and current_user.role_type not in (
        RoleType.division_head, RoleType.office_manager
    ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    _log(db, current_user.id, "update", "user", user.id, f"Updated user {user.email}")
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    _log(db, current_user.id, "deactivate", "user", user.id, f"Deactivated user {user.email}")


@router.get("/audit-logs")
def list_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head, RoleType.office_manager)),
):
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": l.id,
            "actor_name": l.actor.name if l.actor else "מערכת",
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "details": l.details,
            "created_at": l.created_at,
        }
        for l in logs
    ]


def _log(db: Session, actor_id: int, action: str, entity: str, entity_id: int, details: str):
    db.add(AuditLog(
        actor_user_id=actor_id,
        action=action,
        entity_type=entity,
        entity_id=entity_id,
        details=details,
    ))
    db.commit()


@router.delete("/admin/reset-data", status_code=200)
def reset_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Hard reset: delete all work items, emails, reports, audit logs, and notifications.
    Users, teams, and org config are preserved.
    Division head only.
    """
    if current_user.role_type != RoleType.division_head:
        raise HTTPException(status_code=403, detail="Division head only")

    db.query(Notification).delete()
    db.query(AuditLog).delete()
    db.query(ReportSubmission).delete()
    # Nullify FK before deleting emails to avoid constraint errors
    db.query(WorkItem).update({"source_email_id": None}, synchronize_session=False)
    db.query(Email).update({"linked_item_id": None}, synchronize_session=False)
    db.query(WorkItem).delete()
    db.query(Email).delete()
    db.commit()

    return {"status": "ok", "message": "All work data cleared. Users and teams preserved."}


@router.post("/admin/trigger-report-prompts", status_code=200)
async def trigger_report_prompts(
    user_ids: Optional[List[int]] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger report prompts for given user IDs (or all active users if none specified).
    Division head only.
    """
    if current_user.role_type != RoleType.division_head:
        raise HTTPException(status_code=403, detail="Division head only")

    from app.email.notifications import dispatch_report_prompt

    if user_ids:
        targets = db.query(User).filter(User.id.in_(user_ids), User.is_active == True).all()
    else:
        targets = db.query(User).filter(User.is_active == True).all()

    sent = []
    for user in targets:
        open_tasks = db.query(WorkItem).filter(
            WorkItem.assignee_user_id == user.id,
            WorkItem.status.notin_(["completed", "cancelled", "archived"]),
        ).all()
        await dispatch_report_prompt(db, user, open_tasks)
        sent.append({"id": user.id, "name": user.name, "email": user.notification_email or user.email})

    return {"status": "ok", "sent_to": sent}


@router.post("/admin/send-test-email", status_code=200)
async def send_test_email(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a simple connectivity test email to all users that have a notification_email set.
    Division head only.
    """
    if current_user.role_type != RoleType.division_head:
        raise HTTPException(status_code=403, detail="Division head only")

    from app.email.gmail import send_email
    from app.org_config import load_org_config

    config = load_org_config(db)
    app_url = str(config.get("app_url") or "https://web-production-21d65.up.railway.app")

    users_with_notif = db.query(User).filter(
        User.notification_email.isnot(None),
        User.is_active == True,
    ).all()

    sent = []
    failed = []
    for user in users_with_notif:
        subject = f"[FinAgent] מייל בדיקה - {user.name}"
        body_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="utf-8"><style>
body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; direction: rtl; }}
.card {{ background: white; border-radius: 8px; padding: 24px; max-width: 600px; margin: auto; }}
h2 {{ color: #1a365d; }}
.btn {{ display: inline-block; background: #2b6cb0; color: white; padding: 10px 20px;
        text-decoration: none; border-radius: 5px; margin-top: 16px; }}
</style></head>
<body><div class="card">
<h2>FinAgent - מייל בדיקה</h2>
<p>שלום {user.name},</p>
<p>זהו מייל בדיקה מ-FinAgent. המערכת עובדת תקין והודעות ישלחו לכתובת זו.</p>
<p>תפקיד: {user.role_type}</p>
<a href="{app_url}" class="btn">כניסה למערכת</a>
<div style="margin-top:24px;font-size:12px;color:#888;">FinAgent | אגף פיננסי</div>
</div></body></html>"""
        try:
            await send_email(to=user.notification_email, subject=subject, body_html=body_html)
            sent.append({"name": user.name, "email": user.notification_email})
        except Exception as e:
            failed.append({"name": user.name, "email": user.notification_email, "error": str(e)})

    return {"status": "ok", "sent": sent, "failed": failed}


@router.post("/admin/migrate-notification-email", status_code=200)
def migrate_notification_email(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    One-time migration: add notification_email column if missing, then set real Gmail addresses
    for the four key users. Division head only.
    """
    if current_user.role_type != RoleType.division_head:
        raise HTTPException(status_code=403, detail="Division head only")

    from sqlalchemy import text

    # Add column if it doesn't exist (SQLite allows this safely)
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN notification_email VARCHAR(200)"))
        db.commit()
    except Exception:
        pass  # Column already exists — that's fine

    # Map BOI email → real notification email
    mappings = {
        "yosis@boi.org.il": "yossef.saadon@gmail.com",
        "rachel.levy@boi.org.il": "yosis1000@gmail.com",
        "amit.golan@boi.org.il": "newsflow.app@gmail.com",
        "david.cohen@boi.org.il": "saadons.family@gmail.com",
    }

    updated = []
    for boi_email, gmail in mappings.items():
        user = db.query(User).filter(User.email == boi_email).first()
        if user:
            user.notification_email = gmail
            updated.append({"name": user.name, "boi_email": boi_email, "notification_email": gmail})

    db.commit()
    return {"status": "ok", "updated": updated}


@router.post("/admin/trigger-email-poll", status_code=200)
async def trigger_email_poll(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger one email poll cycle. Division head only."""
    if current_user.role_type != RoleType.division_head:
        raise HTTPException(status_code=403, detail="Division head only")

    from app.email.processor import process_incoming_emails
    from app.config import get_settings
    settings = get_settings()
    await process_incoming_emails(db, settings.gmail_address)
    return {"status": "ok", "message": "Email poll triggered"}
