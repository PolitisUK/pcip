"""Fail-safe active-system deletion for participant privacy requests.

The worker deletes only data selected through organisation, participant and
optional study scope.  Media objects are removed before their database rows;
any storage error leaves the request retryable and prevents a false COMPLETE
state.  Backup expiry is deliberately outside this live-system worker.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import (
    ActivityResponse,
    AuditEvent,
    EvidenceConfidenceAssessment,
    EvidenceFile,
    Participant,
    ParticipantAppAccessCode,
    ParticipantInvitation,
    ParticipantMessage,
    ParticipantPrivacyRequest,
    OutboxEmail,
    PublicAuthSession,
    ResearchAnalysisSuggestion,
    ResearchTheme,
    StudyEnrolment,
    StudyGovernance,
)
from .storage import StorageBackend


ACTIVE_DELETION_CATEGORIES = (
    "activity_responses",
    "drafts",
    "messages",
    "evidence_records",
    "live_media_objects",
    "research_derivatives",
    "enrolments",
    "invitations",
    "participant_sessions",
    "participant_profile",
    "prospectively_scoped_outbox_emails",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_ids(value: str) -> set[int]:
    try:
        decoded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return set()
    return {item for item in decoded if isinstance(item, int)} if isinstance(decoded, list) else set()


def revoke_participant_access(
    db: Session,
    *,
    organisation_id: int,
    participant_id: int,
    study_id: int | None,
) -> None:
    """Immediately stop study access and invalidate the matching invitations."""
    enrolment_query = select(StudyEnrolment).where(
        StudyEnrolment.organisation_id == organisation_id,
        StudyEnrolment.participant_id == participant_id,
    )
    invitation_query = select(ParticipantInvitation).where(
        ParticipantInvitation.organisation_id == organisation_id,
        ParticipantInvitation.participant_id == participant_id,
    )
    if study_id is not None:
        enrolment_query = enrolment_query.where(StudyEnrolment.study_id == study_id)
        invitation_query = invitation_query.where(ParticipantInvitation.study_id == study_id)
    for enrolment in db.scalars(enrolment_query):
        enrolment.status = "withdrawn"
    invitations = list(db.scalars(invitation_query))
    invitation_ids = [row.id for row in invitations]
    for invitation in invitations:
        invitation.revoked_at = invitation.revoked_at or utcnow()
    if invitation_ids:
        db.execute(
            update(PublicAuthSession)
            .where(
                PublicAuthSession.participant_invitation_id.in_(invitation_ids),
                PublicAuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )


def _delete_research_derivatives(
    db: Session,
    *,
    organisation_id: int,
    study_id: int | None,
    response_ids: set[int],
) -> None:
    if not response_ids:
        return
    suggestions_query = select(ResearchAnalysisSuggestion).where(
        ResearchAnalysisSuggestion.organisation_id == organisation_id,
        ResearchAnalysisSuggestion.source_response_id.in_(response_ids),
    )
    if study_id is not None:
        suggestions_query = suggestions_query.where(ResearchAnalysisSuggestion.study_id == study_id)
    suggestion_ids = {row.id for row in db.scalars(suggestions_query)}
    if suggestion_ids:
        for theme in db.scalars(select(ResearchTheme).where(ResearchTheme.organisation_id == organisation_id)):
            if _json_ids(theme.source_suggestion_ids_json) & suggestion_ids:
                db.delete(theme)
        db.execute(delete(ResearchAnalysisSuggestion).where(ResearchAnalysisSuggestion.id.in_(suggestion_ids)))
    for assessment in db.scalars(
        select(EvidenceConfidenceAssessment).where(EvidenceConfidenceAssessment.organisation_id == organisation_id)
    ):
        response_references = _json_ids(assessment.supporting_response_ids_json) | _json_ids(assessment.contradicting_response_ids_json)
        if response_references & response_ids:
            db.delete(assessment)


def process_deletion_request(db: Session, storage: StorageBackend, request: ParticipantPrivacyRequest) -> bool:
    """Attempt one idempotent active-system deletion pass.

    Returns True only after the required live media and rows have been removed.
    A storage/database failure is retained as retryable metadata and never
    represented as successful participant deletion.
    """
    if request.status == "completed":
        return True
    if request.participant_id is None:
        request.status = "requires_controller_review"
        request.retriable = False
        request.last_error_code = "identity_link_unavailable"
        db.commit()
        return False

    participant_id = request.participant_id
    organisation_id = request.organisation_id
    study_id = request.study_id if request.scope == "study" else None
    governed_study_ids = [study_id] if study_id is not None else list(
        db.scalars(
            select(StudyEnrolment.study_id).where(
                StudyEnrolment.organisation_id == organisation_id,
                StudyEnrolment.participant_id == participant_id,
            )
        )
    )
    governance_rows = list(
        db.scalars(
            select(StudyGovernance).where(
                StudyGovernance.organisation_id == organisation_id,
                StudyGovernance.study_id.in_(governed_study_ids),
            )
        )
    )
    if any(row.deletion_retention_exception.strip().lower() not in {"", "none", "none."} for row in governance_rows):
        request.status = "requires_controller_review"
        request.retriable = False
        request.retention_exceptions_json = json.dumps(["controller_documented_retention_exception"])
        request.last_error_code = ""
        db.commit()
        return False
    request.status = "in_progress"
    request.retriable = False
    request.started_at = request.started_at or utcnow()
    request.last_error_code = ""
    db.commit()

    try:
        evidence_query = select(EvidenceFile).where(
            EvidenceFile.organisation_id == organisation_id,
            EvidenceFile.participant_id == participant_id,
        )
        response_query = select(ActivityResponse).where(
            ActivityResponse.organisation_id == organisation_id,
            ActivityResponse.participant_id == participant_id,
        )
        message_query = select(ParticipantMessage).where(
            ParticipantMessage.organisation_id == organisation_id,
            ParticipantMessage.participant_id == participant_id,
        )
        enrolment_query = select(StudyEnrolment).where(
            StudyEnrolment.organisation_id == organisation_id,
            StudyEnrolment.participant_id == participant_id,
        )
        invitation_query = select(ParticipantInvitation).where(
            ParticipantInvitation.organisation_id == organisation_id,
            ParticipantInvitation.participant_id == participant_id,
        )
        if study_id is not None:
            evidence_query = evidence_query.where(EvidenceFile.study_id == study_id)
            response_query = response_query.where(ActivityResponse.study_id == study_id)
            message_query = message_query.where(ParticipantMessage.study_id == study_id)
            enrolment_query = enrolment_query.where(StudyEnrolment.study_id == study_id)
            invitation_query = invitation_query.where(ParticipantInvitation.study_id == study_id)

        evidence_rows = list(db.scalars(evidence_query))
        # Do not remove an evidence row before live blob deletion confirms.
        for row in evidence_rows:
            storage.delete(row.stored_name)

        response_rows = list(db.scalars(response_query))
        response_ids = {row.id for row in response_rows}
        _delete_research_derivatives(
            db,
            organisation_id=organisation_id,
            study_id=study_id,
            response_ids=response_ids,
        )
        for row in evidence_rows:
            db.delete(row)
        for row in response_rows:
            db.delete(row)
        for row in db.scalars(message_query):
            db.delete(row)

        scoped_outbox_query = select(OutboxEmail).where(
            OutboxEmail.organisation_id == organisation_id,
            OutboxEmail.participant_id == participant_id,
        )
        if study_id is not None:
            scoped_outbox_query = scoped_outbox_query.where(OutboxEmail.study_id == study_id)
        for row in db.scalars(scoped_outbox_query):
            db.delete(row)

        invitations = list(db.scalars(invitation_query))
        invitation_ids = [row.id for row in invitations]
        if invitation_ids:
            db.execute(delete(PublicAuthSession).where(PublicAuthSession.participant_invitation_id.in_(invitation_ids)))
            db.execute(
                delete(ParticipantAppAccessCode).where(
                    ParticipantAppAccessCode.participant_invitation_id.in_(invitation_ids)
                )
            )
        for row in invitations:
            db.delete(row)
        for row in db.scalars(enrolment_query):
            db.delete(row)

        # Generic historical audit entries may contain participant identifiers;
        # the dedicated privacy request retains only minimised lifecycle state.
        db.execute(
            delete(AuditEvent).where(
                AuditEvent.organisation_id == organisation_id,
                AuditEvent.entity_type == "participant",
                AuditEvent.entity_id == str(participant_id),
            )
        )

        if request.scope == "account":
            participant = db.get(Participant, participant_id)
            if participant is not None and participant.organisation_id == organisation_id:
                db.delete(participant)
            request.participant_id = None

        request.categories_json = json.dumps(ACTIVE_DELETION_CATEGORIES)
        request.status = "completed"
        request.retriable = False
        request.completed_at = utcnow()
        request.last_error_code = ""
        db.commit()
        return True
    except Exception as exc:  # exact storage/database details must not reach participants
        db.rollback()
        refreshed = db.get(ParticipantPrivacyRequest, request.id)
        if refreshed is not None:
            refreshed.status = "failed_retrying"
            refreshed.retriable = True
            refreshed.retry_count = int(refreshed.retry_count or 0) + 1
            refreshed.last_error_code = exc.__class__.__name__[:80]
            db.commit()
        return False
