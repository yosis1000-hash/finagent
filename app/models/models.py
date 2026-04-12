from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, Text, Boolean, DateTime, Date,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class RoleType(str, enum.Enum):
    division_head = "division_head"
    department_head = "department_head"
    section_head = "section_head"
    office_manager = "office_manager"
    economist = "economist"
    student = "student"
    advisor = "advisor"
    team_lead = "team_lead"
    external = "external"


class ReportFrequency(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    none = "none"


class ItemType(str, enum.Enum):
    project = "project"
    task = "task"
    subtask = "subtask"
    followup = "followup"
    reminder = "reminder"


class ItemStatus(str, enum.Enum):
    # Project
    planning = "planning"
    active = "active"
    on_hold = "on_hold"
    # Task/Subtask
    open = "open"
    in_progress = "in_progress"
    pending_review = "pending_review"
    # Follow-up
    waiting = "waiting"
    responded = "responded"
    overdue = "overdue"
    # Shared
    completed = "completed"
    cancelled = "cancelled"
    archived = "archived"
    closed = "closed"


class Priority(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    role_type: Mapped[str] = mapped_column(
        SAEnum(RoleType), nullable=False, default=RoleType.economist
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    report_frequency: Mapped[str] = mapped_column(
        SAEnum(ReportFrequency), nullable=False, default=ReportFrequency.weekly
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    parent: Mapped[Optional["User"]] = relationship("User", remote_side="User.id", back_populates="reports")
    reports: Mapped[list["User"]] = relationship("User", back_populates="parent")
    team_memberships: Mapped[list["TeamMember"]] = relationship("TeamMember", back_populates="user", foreign_keys="TeamMember.user_id")
    led_teams: Mapped[list["Team"]] = relationship("Team", back_populates="lead")
    assigned_items: Mapped[list["WorkItem"]] = relationship("WorkItem", back_populates="assignee", foreign_keys="WorkItem.assignee_user_id")
    reported_items: Mapped[list["WorkItem"]] = relationship("WorkItem", back_populates="reporter", foreign_keys="WorkItem.reporter_user_id")
    report_submissions: Mapped[list["ReportSubmission"]] = relationship("ReportSubmission", back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    focus: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lead_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    lead: Mapped[Optional[User]] = relationship("User", back_populates="led_teams")
    members: Mapped[list["TeamMember"]] = relationship("TeamMember", back_populates="team")
    work_items: Mapped[list["WorkItem"]] = relationship("WorkItem", back_populates="team")


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    team: Mapped[Team] = relationship("Team", back_populates="members")
    user: Mapped[User] = relationship("User", back_populates="team_memberships", foreign_keys=[user_id])


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(SAEnum(ItemType), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(SAEnum(ItemStatus), nullable=False)
    priority: Mapped[Optional[str]] = mapped_column(SAEnum(Priority), nullable=True)
    assignee_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    reporter_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    team_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams.id"), nullable=True
    )
    parent_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("work_items.id"), nullable=True
    )
    deadline: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_email_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("emails.id"), nullable=True
    )
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array string
    # Follow-up specific
    awaited_from_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    expected_by: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    # Reminder specific
    reminder_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reminder_target_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    reminder_delivery_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    assignee: Mapped[Optional[User]] = relationship("User", back_populates="assigned_items", foreign_keys=[assignee_user_id])
    reporter: Mapped[Optional[User]] = relationship("User", back_populates="reported_items", foreign_keys=[reporter_user_id])
    team: Mapped[Optional[Team]] = relationship("Team", back_populates="work_items")
    parent_item: Mapped[Optional["WorkItem"]] = relationship("WorkItem", remote_side="WorkItem.id", back_populates="sub_items")
    sub_items: Mapped[list["WorkItem"]] = relationship("WorkItem", back_populates="parent_item")
    source_email: Mapped[Optional["Email"]] = relationship("Email", foreign_keys=[source_email_id], primaryjoin="WorkItem.source_email_id == Email.id")
    activity_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="work_item")
    notifications: Mapped[list["Notification"]] = relationship("Notification", back_populates="work_item")


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gmail_message_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sender_email: Mapped[str] = mapped_column(String(200), nullable=False)
    recipients_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_extracted_tasks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    linked_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("work_items.id"), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    linked_item: Mapped[Optional[WorkItem]] = relationship("WorkItem", foreign_keys=[linked_item_id], primaryjoin="Email.linked_item_id == WorkItem.id")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    work_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("work_items.id"), nullable=True
    )
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    actor: Mapped[Optional[User]] = relationship("User", back_populates="audit_logs")
    work_item: Mapped[Optional[WorkItem]] = relationship("WorkItem", back_populates="activity_logs")


class ReportSubmission(Base):
    __tablename__ = "report_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    report_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_score_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    period_start: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String(50), default="web")  # web | email

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="report_submissions")


class OrgConfig(Base):
    """Single-row table holding org-wide configuration as a JSON blob."""
    __tablename__ = "org_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_email: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    work_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("work_items.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        SAEnum(NotificationStatus), default=NotificationStatus.pending
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    work_item: Mapped[Optional[WorkItem]] = relationship("WorkItem", back_populates="notifications")
