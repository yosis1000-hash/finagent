from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Team, TeamMember, User, RoleType, AuditLog
from app.schemas.schemas import TeamCreate, TeamUpdate, TeamOut, TeamMemberAdd
from app.auth.auth import get_current_user, require_roles

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/", response_model=List[TeamOut])
def list_teams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Team).filter(Team.is_active == True).all()


@router.get("/{team_id}")
def get_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    member_users = [db.query(User).filter(User.id == m.user_id).first() for m in members]
    return {
        "id": team.id,
        "name": team.name,
        "focus": team.focus,
        "lead_user_id": team.lead_user_id,
        "is_active": team.is_active,
        "created_at": team.created_at,
        "members": [
            {"id": u.id, "name": u.name, "email": u.email, "role_type": u.role_type}
            for u in member_users if u
        ],
    }


@router.post("/", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head, RoleType.section_head)),
):
    team = Team(**payload.model_dump())
    db.add(team)
    db.commit()
    db.refresh(team)
    _log(db, current_user.id, "create", "team", team.id, f"Created team {team.name}")
    return team


@router.put("/{team_id}", response_model=TeamOut)
def update_team(
    team_id: int,
    payload: TeamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head, RoleType.section_head)),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(team, field, value)
    db.commit()
    db.refresh(team)
    return team


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(
    team_id: int,
    payload: TeamMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head, RoleType.section_head)),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == payload.user_id).first():
        raise HTTPException(status_code=400, detail="User already in team")
    member = TeamMember(team_id=team_id, user_id=payload.user_id)
    db.add(member)
    db.commit()
    _log(db, current_user.id, "add_member", "team", team_id, f"Added user {payload.user_id} to team {team_id}")
    return {"message": "Member added"}


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    team_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleType.division_head, RoleType.section_head)),
):
    member = db.query(TeamMember).filter(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()


def _log(db: Session, actor_id: int, action: str, entity: str, entity_id: int, details: str):
    db.add(AuditLog(
        actor_user_id=actor_id, action=action,
        entity_type=entity, entity_id=entity_id, details=details,
    ))
    db.commit()
