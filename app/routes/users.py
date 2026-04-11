from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, RoleType, AuditLog
from app.schemas.schemas import UserCreate, UserUpdate, UserOut
from app.auth.auth import get_current_user, hash_password, require_roles

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


@router.get("/org-tree")
def get_org_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the full org hierarchy as a nested structure."""
    if current_user.role_type not in (RoleType.division_head, RoleType.office_manager):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    all_users = db.query(User).filter(User.is_active == True).all()

    def build_node(user: User):
        children = [u for u in all_users if u.parent_id == user.id]
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role_type": user.role_type,
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


def _log(db: Session, actor_id: int, action: str, entity: str, entity_id: int, details: str):
    db.add(AuditLog(
        actor_user_id=actor_id,
        action=action,
        entity_type=entity,
        entity_id=entity_id,
        details=details,
    ))
    db.commit()
