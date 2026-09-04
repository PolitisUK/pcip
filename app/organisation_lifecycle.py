from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Activity,
    ActivityResponse,
    AuditEvent,
    EvidenceConfidenceAssessment,
    EvidenceFile,
    Invitation,
    OrganisationMembership,
    OutboxEmail,
    Participant,
    ParticipantAppAccessCode,
    ParticipantInvitation,
    ParticipantMessage,
    ParticipantPrivacyRequest,
    Project,
    ResearchAnalysisSuggestion,
    ResearchTheme,
    Study,
    StudyAccess,
    StudyConsentBundle,
    StudyConsentDocument,
    StudyEnrolment,
    StudyGovernance,
    StudyMethodologyConfiguration,
    User,
)


# These events describe administration of an otherwise empty organisation. They
# are removed with that organisation only after the deletion event has been
# durably recorded against the platform administrator's active organisation.
DISPOSABLE_LIFECYCLE_AUDIT_ACTIONS = frozenset(
    {
        "platform_admin.dashboard_viewed",
        "platform_admin.organisation_archived",
        "platform_admin.organisation_created",
        "platform_admin.organisation_restored",
    }
)


# Every model with a direct organisation_id, except memberships and audit events
# which receive the special handling above. Keeping this list explicit makes the
# safety policy reviewable; a regression test fails if a new scoped model is not
# classified here.
MEANINGFUL_ORGANISATION_MODELS = (
    (User, "user accounts"),
    (Project, "projects"),
    (Study, "studies"),
    (StudyGovernance, "study governance records"),
    (StudyConsentDocument, "study consent documents"),
    (StudyConsentBundle, "study consent bundles"),
    (StudyMethodologyConfiguration, "methodology records"),
    (Participant, "participants"),
    (StudyEnrolment, "study enrolments"),
    (Activity, "activities"),
    (ActivityResponse, "submissions or responses"),
    (EvidenceFile, "evidence files"),
    (ParticipantMessage, "messages"),
    (ParticipantInvitation, "participant invitations"),
    (ParticipantAppAccessCode, "participant app access codes"),
    (Invitation, "team invitations"),
    (ParticipantPrivacyRequest, "privacy records"),
    (ResearchAnalysisSuggestion, "research analysis records"),
    (EvidenceConfidenceAssessment, "evidence assessments"),
    (ResearchTheme, "research themes"),
    (OutboxEmail, "email delivery records"),
    (StudyAccess, "study access records"),
)


@dataclass(frozen=True)
class OrganisationDeletionAssessment:
    blocking_counts: dict[str, int]
    membership_count: int
    lifecycle_audit_count: int

    @property
    def can_delete(self) -> bool:
        return not self.blocking_counts


def assess_organisation_deletion(
    db: Session,
    organisation_id: int,
) -> OrganisationDeletionAssessment:
    """Return a conservative, non-sensitive deletion assessment."""

    blocking_counts: dict[str, int] = {}
    for model, label in MEANINGFUL_ORGANISATION_MODELS:
        count = int(
            db.scalar(
                select(func.count(model.id)).where(
                    model.organisation_id == organisation_id
                )
            )
            or 0
        )
        if count:
            blocking_counts[label] = count

    retained_audit_count = int(
        db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organisation_id == organisation_id,
                AuditEvent.action.not_in(DISPOSABLE_LIFECYCLE_AUDIT_ACTIONS),
            )
        )
        or 0
    )
    if retained_audit_count:
        blocking_counts["audit records"] = retained_audit_count

    membership_count = int(
        db.scalar(
            select(func.count(OrganisationMembership.id)).where(
                OrganisationMembership.organisation_id == organisation_id
            )
        )
        or 0
    )
    lifecycle_audit_count = int(
        db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organisation_id == organisation_id,
                AuditEvent.action.in_(DISPOSABLE_LIFECYCLE_AUDIT_ACTIONS),
            )
        )
        or 0
    )
    return OrganisationDeletionAssessment(
        blocking_counts=blocking_counts,
        membership_count=membership_count,
        lifecycle_audit_count=lifecycle_audit_count,
    )
