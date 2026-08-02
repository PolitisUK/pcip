from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Role(str, Enum):
    owner = "owner"
    admin = "admin"
    researcher = "researcher"
    observer = "observer"


class ProjectStatus(str, Enum):
    draft = "draft"
    live = "live"
    closed = "closed"
    archived = "archived"


class StudyStatus(str, Enum):
    draft = "draft"
    recruiting = "recruiting"
    live = "live"
    paused = "paused"
    closed = "closed"


class ParticipantStatus(str, Enum):
    prospective = "prospective"
    invited = "invited"
    active = "active"
    completed = "completed"
    withdrawn = "withdrawn"


class ConsentStatus(str, Enum):
    pending = "pending"
    granted = "granted"
    withdrawn = "withdrawn"


class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    users: Mapped[list[User]] = relationship(back_populates="organisation")
    memberships: Mapped[list[OrganisationMembership]] = relationship(
        back_populates="organisation"
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organisation_id", "email"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_provider: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(30), default=Role.researcher.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    organisation: Mapped[Organisation] = relationship(back_populates="users")
    memberships: Mapped[list[OrganisationMembership]] = relationship(
        back_populates="user"
    )


Index("ux_users_email_normalized", func.lower(User.email), unique=True)


class OrganisationMembership(Base):
    __tablename__ = "organisation_memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organisation_id",
            name="uq_organisation_memberships_user_org",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisations.id"),
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(30),
        default=Role.researcher.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    user: Mapped[User] = relationship(back_populates="memberships")
    organisation: Mapped[Organisation] = relationship(
        back_populates="memberships"
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organisation_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default=ProjectStatus.draft.value)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Study(Base):
    __tablename__ = "studies"
    __table_args__ = (UniqueConstraint("organisation_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, default="")
    methodology: Mapped[str] = mapped_column(String(80), default="diary")
    status: Mapped[str] = mapped_column(String(30), default=StudyStatus.draft.value)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    demographics_schema_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("organisation_id", "reference"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    reference: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=ParticipantStatus.prospective.value)
    consent_status: Mapped[str] = mapped_column(String(30), default=ConsentStatus.pending.value)
    communication_preference: Mapped[str] = mapped_column(String(30), default="email")
    tags: Mapped[str] = mapped_column(Text, default="")
    demographics_json: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StudyEnrolment(Base):
    __tablename__ = "study_enrolments"
    __table_args__ = (UniqueConstraint("study_id", "participant_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="enrolled")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text, default="")
    activity_type: Mapped[str] = mapped_column(String(50), default="long_text")
    options_json: Mapped[str] = mapped_column(Text, default="[]")
    position: Mapped[int] = mapped_column(Integer, default=1)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    release_offset_days: Mapped[int] = mapped_column(Integer, default=0)
    due_offset_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActivityResponse(Base):
    __tablename__ = "activity_responses"
    __table_args__ = (UniqueConstraint("activity_id", "participant_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    response_id: Mapped[int | None] = mapped_column(ForeignKey("activity_responses.id"), nullable=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256_hex: Mapped[str] = mapped_column(String(64), default="")
    scan_status: Mapped[str] = mapped_column(String(30), default="pending")
    scan_detail: Mapped[str] = mapped_column(Text, default="")
    storage_provider: Mapped[str] = mapped_column(String(30), default="local")
    blob_uri: Mapped[str] = mapped_column(Text, default="")
    scan_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ParticipantMessage(Base):
    __tablename__ = "participant_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    sender_type: Mapped[str] = mapped_column(String(30))
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    internal_note: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ParticipantInvitation(Base):
    __tablename__ = "participant_invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicTokenExchange(Base):
    __tablename__ = "public_token_exchanges"
    __table_args__ = (UniqueConstraint("scope", "token_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(60), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicAuthSession(Base):
    __tablename__ = "public_auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(60), index=True)
    session_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_reset_id: Mapped[int | None] = mapped_column(ForeignKey("password_resets.id"), nullable=True, index=True)
    invitation_id: Mapped[int | None] = mapped_column(ForeignKey("invitations.id"), nullable=True, index=True)
    participant_invitation_id: Mapped[int | None] = mapped_column(ForeignKey("participant_invitations.id"), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index(
    "ux_public_auth_sessions_participant_api_active_invitation",
    PublicAuthSession.participant_invitation_id,
    unique=True,
    postgresql_where=(
        (PublicAuthSession.scope == "participant_api")
        & (PublicAuthSession.revoked_at.is_(None))
        & (PublicAuthSession.participant_invitation_id.is_not(None))
    ),
    sqlite_where=(
        (PublicAuthSession.scope == "participant_api")
        & (PublicAuthSession.revoked_at.is_(None))
        & (PublicAuthSession.participant_invitation_id.is_not(None))
    ),
)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEmail(Base):
    __tablename__ = "outbox_emails"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudyAccess(Base):
    __tablename__ = "study_access"
    __table_args__ = (UniqueConstraint("study_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    permission: Mapped[str] = mapped_column(String(20), default="view")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
