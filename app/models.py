from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


def default_outbox_retention_expiry():
    """Safe default for direct model construction; queue_email uses settings."""
    return utcnow() + timedelta(days=30)


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
    # This is deliberately separate from an organisation role.  A customer
    # owner administers only their own organisation; platform administration
    # must be granted through the controlled bootstrap process.
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
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


class StudyGovernance(Base):
    """Controller-supplied launch information; empty values are deliberately incomplete."""

    __tablename__ = "study_governance"
    __table_args__ = (
        UniqueConstraint("study_id", name="uq_study_governance_study"),
        Index("ix_study_governance_scope", "organisation_id", "study_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    controller_name: Mapped[str] = mapped_column(String(200), default="")
    controller_privacy_contact: Mapped[str] = mapped_column(String(255), default="")
    sponsor_name: Mapped[str] = mapped_column(String(200), default="")
    research_contact: Mapped[str] = mapped_column(String(255), default="")
    participant_population: Mapped[str] = mapped_column(Text, default="")
    data_categories: Mapped[str] = mapped_column(Text, default="")
    special_category_data: Mapped[str] = mapped_column(String(30), default="not_assessed")
    article_6_lawful_basis: Mapped[str] = mapped_column(Text, default="")
    article_9_condition: Mapped[str] = mapped_column(Text, default="")
    participation_consent_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    participant_information_available: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_information_available: Mapped[bool] = mapped_column(Boolean, default=False)
    participant_information_reference: Mapped[str] = mapped_column(String(500), default="")
    participant_information_version: Mapped[str] = mapped_column(String(80), default="")
    participant_information_effective_date: Mapped[str] = mapped_column(String(30), default="")
    privacy_notice_reference: Mapped[str] = mapped_column(String(500), default="")
    privacy_notice_version: Mapped[str] = mapped_column(String(80), default="")
    privacy_notice_effective_date: Mapped[str] = mapped_column(String(30), default="")
    consent_text_reference: Mapped[str] = mapped_column(String(500), default="")
    consent_text_version: Mapped[str] = mapped_column(String(80), default="")
    consent_text_effective_date: Mapped[str] = mapped_column(String(30), default="")
    # The current immutable, controller-approved document bundle.  The
    # governance fields above remain for launch-readiness display and legacy
    # records; invitations point at a bundle so later edits cannot rewrite
    # what a participant saw.
    current_consent_bundle_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_consent_bundles.id"), nullable=True, index=True
    )
    retention_description: Mapped[str] = mapped_column(Text, default="")
    deletion_retention_exception: Mapped[str] = mapped_column(Text, default="")
    withdrawal_process_defined: Mapped[bool] = mapped_column(Boolean, default=False)
    deletion_handling_defined: Mapped[bool] = mapped_column(Boolean, default=False)
    features_assessed: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled_features_json: Mapped[str] = mapped_column(Text, default="[]")
    ai_features_disclosed: Mapped[bool] = mapped_column(Boolean, default=False)
    international_transfer_assessment: Mapped[str] = mapped_column(String(30), default="not_assessed")
    ethics_status: Mapped[str] = mapped_column(String(30), default="not_assessed")
    dpia_status: Mapped[str] = mapped_column(String(30), default="not_assessed")
    security_considerations: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StudyConsentDocument(Base):
    """One immutable study-specific participant-facing document version."""

    __tablename__ = "study_consent_documents"
    __table_args__ = (
        UniqueConstraint("study_id", "document_type", "content_sha256", name="uq_study_consent_document_content"),
        Index("ix_study_consent_documents_scope", "organisation_id", "study_id", "document_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(80))
    reference: Mapped[str] = mapped_column(String(500))
    effective_date: Mapped[str] = mapped_column(String(30))
    body: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudyConsentBundle(Base):
    """Immutable three-document binding used for one study invitation."""

    __tablename__ = "study_consent_bundles"
    __table_args__ = (
        UniqueConstraint("study_id", "bundle_sha256", name="uq_study_consent_bundle_content"),
        Index("ix_study_consent_bundles_scope", "organisation_id", "study_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    bundle_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudyConsentBundleDocument(Base):
    """The explicit document-version membership of an immutable bundle."""

    __tablename__ = "study_consent_bundle_documents"
    __table_args__ = (
        UniqueConstraint("bundle_id", "document_type", name="uq_study_consent_bundle_document_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("study_consent_bundles.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("study_consent_documents.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(40))


class StudyMethodologyConfiguration(Base):
    """Researcher-confirmed, version-pinned method and AI boundary for one study."""

    __tablename__ = "study_methodology_configurations"
    __table_args__ = (
        UniqueConstraint("study_id", name="uq_study_methodology_configuration_study"),
        Index("ix_study_methodology_configuration_scope", "organisation_id", "study_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    primary_methodology_id: Mapped[str] = mapped_column(String(30), default="")
    methodology_variant: Mapped[str] = mapped_column(String(80), default="")
    secondary_methodologies_json: Mapped[str] = mapped_column(Text, default="[]")
    # The protocol-builder selections are deliberately stored separately from
    # the controlled-methodology identifiers above.  This retains historical
    # provenance while avoiding a false equivalence between approach, data
    # generation, analysis and theoretical orientation.
    research_approaches_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_methods_json: Mapped[str] = mapped_column(Text, default="[]")
    analysis_approaches_json: Mapped[str] = mapped_column(Text, default="[]")
    theoretical_orientations_json: Mapped[str] = mapped_column(Text, default="[]")
    legacy_methodology_json: Mapped[str] = mapped_column(Text, default="[]")
    research_questions: Mapped[str] = mapped_column(Text, default="")
    protocol_reference: Mapped[str] = mapped_column(String(500), default="")
    protocol_version: Mapped[str] = mapped_column(String(80), default="")
    sampling_approach: Mapped[str] = mapped_column(Text, default="")
    data_collection_plan: Mapped[str] = mapped_column(Text, default="")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_ai_tasks_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    library_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    researcher_notes: Mapped[str] = mapped_column(Text, default="")
    researcher_confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    researcher_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    allow_multiple_entries: Mapped[bool] = mapped_column(Boolean, default=False)
    release_offset_days: Mapped[int] = mapped_column(Integer, default=0)
    due_offset_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActivityResponse(Base):
    __tablename__ = "activity_responses"
    __table_args__ = (
        UniqueConstraint("activity_id", "participant_id", "client_entry_key_hash", name="uq_activity_response_entry_key"),
        Index(
            "uq_activity_response_single_entry",
            "activity_id",
            "participant_id",
            unique=True,
            postgresql_where=text("repeatable = false"),
            sqlite_where=text("repeatable = 0"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    repeatable: Mapped[bool] = mapped_column(Boolean, default=False)
    # Hash only: raw participant idempotency keys never enter the database or
    # audit trail.  Null remains valid for legacy single-response records.
    client_entry_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    __table_args__ = (
        UniqueConstraint(
            "organisation_id",
            "participant_id",
            "activity_id",
            "upload_key_hash",
            name="uq_evidence_participant_upload_key",
        ),
    )
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
    upload_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scan_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ParticipantMessage(Base):
    __tablename__ = "participant_messages"
    __table_args__ = (
        UniqueConstraint(
            "organisation_id",
            "participant_id",
            "study_id",
            "idempotency_key_hash",
            name="uq_participant_message_client_key",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    sender_type: Mapped[str] = mapped_column(String(30))
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    participant_information_reference: Mapped[str] = mapped_column(String(500), default="")
    participant_information_version: Mapped[str] = mapped_column(String(80), default="")
    participant_information_effective_date: Mapped[str] = mapped_column(String(30), default="")
    privacy_notice_reference: Mapped[str] = mapped_column(String(500), default="")
    privacy_notice_version: Mapped[str] = mapped_column(String(80), default="")
    privacy_notice_effective_date: Mapped[str] = mapped_column(String(30), default="")
    consent_text_reference: Mapped[str] = mapped_column(String(500), default="")
    consent_text_version: Mapped[str] = mapped_column(String(80), default="")
    consent_text_effective_date: Mapped[str] = mapped_column(String(30), default="")
    consent_bundle_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_consent_bundles.id"), nullable=True, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ParticipantAppAccessCode(Base):
    """One-time bridge from web consent to the participant app.

    Only a digest is stored. The raw code is displayed once in the authenticated
    participant portal and is never persisted or written to audit detail.
    """

    __tablename__ = "participant_app_access_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    participant_invitation_id: Mapped[int] = mapped_column(
        ForeignKey("participant_invitations.id"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class ParticipantPrivacyRequest(Base):
    """Minimal lifecycle evidence for a participant withdrawal/deletion request.

    ``participant_id`` is cleared after an account deletion so this record can
    prove the request was completed without retaining a live identity link or
    any participant content.  It intentionally has no free-text reason field.
    """

    __tablename__ = "participant_privacy_requests"
    __table_args__ = (
        Index("ix_participant_privacy_request_scope", "organisation_id", "study_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id"), nullable=True)
    study_id: Mapped[int | None] = mapped_column(ForeignKey("studies.id"), nullable=True)
    request_type: Mapped[str] = mapped_column(String(30), index=True)
    scope: Mapped[str] = mapped_column(String(30), default="study")
    status: Mapped[str] = mapped_column(String(40), default="received", index=True)
    retriable: Mapped[bool] = mapped_column(Boolean, default=False)
    categories_json: Mapped[str] = mapped_column(Text, default="[]")
    retention_exceptions_json: Mapped[str] = mapped_column(Text, default="[]")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str] = mapped_column(String(80), default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class ResearchAnalysisSuggestion(Base):
    """Untrusted AI output; never an accepted finding without researcher review."""
    __tablename__ = "research_analysis_suggestions"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    source_response_id: Mapped[int] = mapped_column(ForeignKey("activity_responses.id"), index=True)
    source_snapshot: Mapped[str] = mapped_column(Text)
    suggested_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    provisional_insight: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="awaiting_researcher_review", index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    methodology_id: Mapped[str] = mapped_column(String(30), default="")
    methodology_variant: Mapped[str] = mapped_column(String(80), default="")
    methodology_library_version: Mapped[str] = mapped_column(String(30), default="")
    methodology_rule_references_json: Mapped[str] = mapped_column(Text, default="[]")
    protocol_version: Mapped[str] = mapped_column(String(80), default="")
    evidence_item_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    model_provider: Mapped[str] = mapped_column(String(80), default="")
    model_deployment: Mapped[str] = mapped_column(String(120), default="")
    prompt_template_version: Mapped[str] = mapped_column(String(80), default="research-analysis-v1")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceConfidenceAssessment(Base):
    """Qualitative evidence-strength assessment, never a statistical confidence claim."""
    __tablename__ = "evidence_confidence_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    focus: Mapped[str] = mapped_column(String(200))
    supporting_response_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    contradicting_response_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    category: Mapped[str] = mapped_column(String(30), default="weak")
    explanation: Mapped[str] = mapped_column(Text, default="")
    limitations_json: Mapped[str] = mapped_column(Text, default="[]")
    strengthening_needs_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(30), default="awaiting_researcher_review", index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchTheme(Base):
    """A researcher-authored working theme, linked to reviewed source analysis."""
    __tablename__ = "research_themes"
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    source_suggestion_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(30), default="researcher_draft", index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


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


class DemoImportStatus(Base):
    """Non-sensitive operational state for one controlled fictional import."""
    __tablename__ = "demo_import_statuses"
    dataset: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    phase: Mapped[str] = mapped_column(String(80), default="not_started")
    content_version: Mapped[str] = mapped_column(String(30), default="")
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OutboxEmail(Base):
    __tablename__ = "outbox_emails"
    __table_args__ = (
        Index("ix_outbox_emails_retention_expires_at", "retention_expires_at"),
        Index(
            "ix_outbox_emails_participant_scope",
            "organisation_id",
            "participant_id",
            "study_id",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id"), nullable=True)
    study_id: Mapped[int | None] = mapped_column(ForeignKey("studies.id"), nullable=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    retention_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=default_outbox_retention_expiry)


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
