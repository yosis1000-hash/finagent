from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from app.models.models import RoleType, ReportFrequency, ItemType, ItemStatus, Priority


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    role_type: str


# ─── Users ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role_type: RoleType = RoleType.economist
    parent_id: Optional[int] = None
    report_frequency: ReportFrequency = ReportFrequency.weekly


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role_type: Optional[RoleType] = None
    parent_id: Optional[int] = None
    report_frequency: Optional[ReportFrequency] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    notification_email: Optional[str] = None
    role_type: str
    parent_id: Optional[int]
    report_frequency: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserOutBrief(BaseModel):
    id: int
    name: str
    email: str
    role_type: str

    model_config = {"from_attributes": True}


# ─── Teams ────────────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str
    focus: Optional[str] = None
    lead_user_id: Optional[int] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    focus: Optional[str] = None
    lead_user_id: Optional[int] = None
    is_active: Optional[bool] = None


class TeamOut(BaseModel):
    id: int
    name: str
    focus: Optional[str]
    lead_user_id: Optional[int]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamMemberAdd(BaseModel):
    user_id: int


class WorkItemCreate(BaseModel):
    type: ItemType
    title: str
    description: Optional[str] = None
    status: Optional[ItemStatus] = None
    priority: Optional[Priority] = Priority.medium
    assignee_user_id: Optional[int] = None
    team_id: Optional[int] = None
    parent_item_id: Optional[int] = None
    deadline: Optional[date] = None
    tags: Optional[str] = None
    # Follow-up specific
    awaited_from_user_id: Optional[int] = None
    expected_by: Optional[date] = None
    # Reminder specific
    reminder_message: Optional[str] = None
    reminder_target_ids: Optional[str] = None
    reminder_delivery_at: Optional[datetime] = None


class WorkItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ItemStatus] = None
    priority: Optional[Priority] = None
    assignee_user_id: Optional[int] = None
    team_id: Optional[int] = None
    parent_item_id: Optional[int] = None
    deadline: Optional[date] = None
    tags: Optional[str] = None
    awaited_from_user_id: Optional[int] = None
    expected_by: Optional[date] = None


# ─── Emails ───────────────────────────────────────────────────────────────────

class EmailOut(BaseModel):
    id: int
    gmail_message_id: str
    thread_id: Optional[str]
    sender_email: str
    recipients_json: Optional[str]
    subject: Optional[str]
    body_text: Optional[str]
    has_attachments: bool
    linked_item_id: Optional[int]
    received_at: datetime
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── Work Items ───────────────────────────────────────────────────────────────

class WorkItemOut(BaseModel):
    id: int
    type: str
    title: str
    description: Optional[str]
    status: str
    priority: Optional[str]
    assignee_user_id: Optional[int]
    reporter_user_id: Optional[int]
    team_id: Optional[int]
    parent_item_id: Optional[int]
    source_email_id: Optional[int]
    deadline: Optional[date]
    completed_at: Optional[datetime]
    ai_summary: Optional[str]
    tags: Optional[str]
    awaited_from_user_id: Optional[int]
    expected_by: Optional[date]
    reminder_message: Optional[str]
    reminder_delivery_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    assignee: Optional[UserOutBrief] = None
    reporter: Optional[UserOutBrief] = None
    source_email: Optional[EmailOut] = None

    model_config = {"from_attributes": True}


# ─── Reports ──────────────────────────────────────────────────────────────────

class ReportSubmit(BaseModel):
    report_text: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class ReportOut(BaseModel):
    id: int
    user_id: int
    report_text: Optional[str]
    ai_score: Optional[int]
    ai_score_reasoning: Optional[str]
    period_start: Optional[date]
    period_end: Optional[date]
    submitted_at: datetime
    source: str
    user: Optional[UserOutBrief] = None

    model_config = {"from_attributes": True}


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_open: int
    due_this_week: int
    overdue: int
    completed_this_month: int


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: Optional[int]
    action: str
    entity_type: str
    entity_id: Optional[int]
    details: Optional[str]
    created_at: datetime
    actor: Optional[UserOutBrief] = None

    model_config = {"from_attributes": True}
