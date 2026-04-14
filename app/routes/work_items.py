import json
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
from app.database import get_db
from app.models.models import (
    WorkItem, User, Team, AuditLog, Email,
    RoleType, ItemType, ItemStatus, Priority
)
from app.schemas.schemas import WorkItemCreate, WorkItemUpdate, WorkItemOut
from app.auth.auth import get_current_user, can_create_task, can_create_project

router = APIRouter(prefix="/api/items", tags=["work_items"])


def _scope_filter(query, current_user: User, db: Session):
    """Apply role-based visibility filter to work_items query."""
    role = current_user.role_type
    if role in (RoleType.division_head, RoleType.office_manager):
        return query  # see everything
    if role == RoleType.section_head:
        # own items + direct reports' items
        report_ids = [u.id for u in db.query(User).filter(User.parent_id == current_user.id).all()]
        ids = [current_user.id] + report_ids
        return query.filter(
            or_(
                WorkItem.assignee_user_id.in_(ids),
                WorkItem.reporter_user_id == current_user.id,
            )
        )
    if role == RoleType.economist:
        # Own tasks + team tasks
        team_ids = [
            tm.team_id for tm in current_user.team_memberships
        ]
        return query.filter(
            or_(
                WorkItem.assignee_user_id == current_user.id,
                WorkItem.reporter_user_id == current_user.id,
                WorkItem.team_id.in_(team_ids) if team_ids else False,
            )
        )
    # student, advisor, external - own only
    return query.filter(WorkItem.assignee_user_id == current_user.id)


@router.get("/", response_model=List[WorkItemOut])
def list_items(
    item_type: Optional[str] = Query(None),
    item_status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None),
    team_id: Optional[int] = Query(None),
    parent_item_id: Optional[int] = Query(None),
    my_work: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(WorkItem).options(
        joinedload(WorkItem.assignee),
        joinedload(WorkItem.reporter),
        joinedload(WorkItem.source_email),
    )
    query = _scope_filter(query, current_user, db)

    if my_work:
        query = query.filter(WorkItem.assignee_user_id == current_user.id)
    if item_type:
        query = query.filter(WorkItem.type == item_type)
    if item_status:
        query = query.filter(WorkItem.status == item_status)
    if priority:
        query = query.filter(WorkItem.priority == priority)
    if assignee_id:
        query = query.filter(WorkItem.assignee_user_id == assignee_id)
    if team_id:
        query = query.filter(WorkItem.team_id == team_id)
    if parent_item_id is not None:
        query = query.filter(WorkItem.parent_item_id == parent_item_id)

    return query.order_by(WorkItem.updated_at.desc()).all()


@router.get("/{item_id}", response_model=WorkItemOut)
def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(WorkItem).options(
        joinedload(WorkItem.assignee),
        joinedload(WorkItem.reporter),
        joinedload(WorkItem.source_email),
    ).filter(WorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.get("/{item_id}/activity")
def get_item_activity(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logs = db.query(AuditLog).filter(AuditLog.work_item_id == item_id).order_by(AuditLog.created_at.desc()).all()
    return [
        {
            "id": l.id,
            "actor": l.actor.name if l.actor else "System",
            "action": l.action,
            "details": l.details,
            "created_at": l.created_at,
        }
        for l in logs
    ]


@router.post("/", response_model=WorkItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: WorkItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.type == ItemType.project and not can_create_project(current_user):
        raise HTTPException(status_code=403, detail="Only division head and section heads can create projects")
    if payload.type == ItemType.task and not can_create_task(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions to create tasks")

    # Set default status
    default_status = {
        ItemType.project: ItemStatus.planning,
        ItemType.task: ItemStatus.open,
        ItemType.subtask: ItemStatus.open,
        ItemType.followup: ItemStatus.waiting,
        ItemType.reminder: ItemStatus.open,
    }
    status_val = payload.status or default_status.get(payload.type, ItemStatus.open)

    item = WorkItem(
        type=payload.type,
        title=payload.title,
        description=payload.description,
        status=status_val,
        priority=payload.priority,
        assignee_user_id=payload.assignee_user_id,
        reporter_user_id=current_user.id,
        team_id=payload.team_id,
        parent_item_id=payload.parent_item_id,
        deadline=payload.deadline,
        tags=payload.tags,
        awaited_from_user_id=payload.awaited_from_user_id,
        expected_by=payload.expected_by,
        reminder_message=payload.reminder_message,
        reminder_target_ids=payload.reminder_target_ids,
        reminder_delivery_at=payload.reminder_delivery_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    _log(db, current_user.id, "create", item.id, f"Created {item.type}: {item.title}")
    return item


@router.put("/{item_id}", response_model=WorkItemOut)
def update_item(
    item_id: int,
    payload: WorkItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(WorkItem).filter(WorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Permission: owner, assignee, or management
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager, RoleType.section_head):
        if item.assignee_user_id != current_user.id and item.reporter_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    changes = []
    for field, value in payload.model_dump(exclude_none=True).items():
        old = getattr(item, field)
        if old != value:
            changes.append(f"{field}: {old} → {value}")
            setattr(item, field, value)

    # Auto-set completed_at
    if payload.status in (ItemStatus.completed, ItemStatus.closed, ItemStatus.cancelled) and not item.completed_at:
        item.completed_at = datetime.utcnow()

    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)

    if changes:
        _log(db, current_user.id, "update", item.id, "; ".join(changes))
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(WorkItem).filter(WorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if current_user.role_type not in (RoleType.division_head, RoleType.section_head):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    # Soft-delete by archiving
    item.status = ItemStatus.archived
    item.updated_at = datetime.utcnow()
    db.commit()


def _log(db: Session, actor_id: int, action: str, item_id: int, details: str):
    db.add(AuditLog(
        actor_user_id=actor_id,
        action=action,
        entity_type="work_item",
        entity_id=item_id,
        work_item_id=item_id,
        details=details,
    ))
    db.commit()
