"""Fixed, password-preserving invitation rebind for the Apple store reviewer.

This is deliberately not a CLI or a general credential migration facility.
Only the protected production-operation worker can invoke the parameterless
``execute_apple_reviewer_invitation_rebind`` entry point.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import (
    AuditEvent,
    ConsentStatus,
    Organisation,
    Participant,
    ParticipantInvitation,
    ParticipantPasswordCredential,
    ParticipantStatus,
    Project,
    Study,
    StudyConsentBundleDocument,
    StudyConsentDocument,
    StudyEnrolment,
    StudyGovernance,
)


class StoreReviewerInvitationRebindError(RuntimeError):
    """Raised when the fixed reviewer transition is unsafe or ambiguous."""


APPLE_PARTICIPANT_ID = 36
APPLE_SOURCE_INVITATION_ID = 6
APPLE_DESTINATION_INVITATION_ID = 11
APPLE_PARTICIPANT_REFERENCE = "APPLE-REVIEWER-001"
APPLE_LOGIN_IDENTIFIER = "apple-reviewer"
APPLE_ORGANISATION_NAME = "Citizen Centric – Apple Review"
APPLE_PROJECT_TITLE = "App Review Demonstration"
APPLE_STUDY_CODE = "APPLE-REVIEW-STUDY"
APPLE_DOCUMENT_VERSION = "1.1"
REBIND_AUDIT_ACTION = "participant.password_credential_store_reviewer_rebound"
REQUIRED_DOCUMENT_TYPES = {
    "participant_information",
    "privacy_notice",
    "consent_text",
}


@dataclass(frozen=True)
class CredentialSnapshot:
    id: int
    organisation_id: int
    participant_id: int
    login_identifier_normalised: str
    password_hash: str
    enabled: bool
    created_at: object
    rotated_at: object


@dataclass(frozen=True)
class ParticipantSnapshot:
    id: int
    organisation_id: int
    reference: str
    name: str
    email: str | None
    phone: str | None
    status: str
    consent_status: str
    is_store_reviewer: bool
    communication_preference: str
    tags: str
    demographics_json: str
    notes: str
    created_by_id: int
    created_at: object
    updated_at: object


@dataclass(frozen=True)
class StoreReviewerInvitationRebindResult:
    participant_id: int
    credential_id: int
    source_invitation_id: int
    destination_invitation_id: int
    organisation_id: int
    project_id: int
    study_id: int
    destination_bundle_id: int
    document_version: str
    changed: bool
    participant_unchanged: bool
    username_unchanged: bool
    password_unchanged: bool
    scope_unchanged: bool
    consent_unchanged: bool
    consent_status: str
    store_reviewer_designation: bool
    credential_enabled: bool

    def approved_result(self) -> dict[str, object]:
        """Return only non-sensitive verification evidence."""
        return asdict(self)


def _credential_snapshot(credential: ParticipantPasswordCredential) -> CredentialSnapshot:
    return CredentialSnapshot(
        id=credential.id,
        organisation_id=credential.organisation_id,
        participant_id=credential.participant_id,
        login_identifier_normalised=credential.login_identifier_normalised,
        password_hash=credential.password_hash,
        enabled=bool(credential.enabled),
        created_at=credential.created_at,
        rotated_at=credential.rotated_at,
    )


def _participant_snapshot(participant: Participant) -> ParticipantSnapshot:
    return ParticipantSnapshot(
        id=participant.id,
        organisation_id=participant.organisation_id,
        reference=participant.reference,
        name=participant.name,
        email=participant.email,
        phone=participant.phone,
        status=participant.status,
        consent_status=participant.consent_status,
        is_store_reviewer=bool(participant.is_store_reviewer),
        communication_preference=participant.communication_preference,
        tags=participant.tags,
        demographics_json=participant.demographics_json,
        notes=participant.notes,
        created_by_id=participant.created_by_id,
        created_at=participant.created_at,
        updated_at=participant.updated_at,
    )


def _require_exactly_one(rows: list[object], message: str):
    if len(rows) != 1:
        raise StoreReviewerInvitationRebindError(message)
    return rows[0]


def _validate_correlation_id(correlation_id: str) -> str:
    if not isinstance(correlation_id, str):
        raise StoreReviewerInvitationRebindError("The operation correlation is invalid.")
    try:
        parsed = UUID(correlation_id)
    except (TypeError, ValueError) as exc:
        raise StoreReviewerInvitationRebindError(
            "The operation correlation is invalid."
        ) from exc
    if str(parsed) != correlation_id.lower():
        raise StoreReviewerInvitationRebindError("The operation correlation is invalid.")
    return correlation_id


def _eligible_pending_invitations(
    db: Session,
    *,
    participant: Participant,
    study: Study,
    at: datetime,
) -> list[ParticipantInvitation]:
    return list(
        db.scalars(
            select(ParticipantInvitation)
            .where(
                ParticipantInvitation.organisation_id == participant.organisation_id,
                ParticipantInvitation.participant_id == participant.id,
                ParticipantInvitation.study_id == study.id,
                ParticipantInvitation.accepted_at.is_(None),
                ParticipantInvitation.revoked_at.is_(None),
                ParticipantInvitation.expires_at > at,
            )
            .order_by(ParticipantInvitation.id)
            .with_for_update()
        )
    )


def _require_current_bundle(
    db: Session,
    *,
    destination: ParticipantInvitation,
    governance: StudyGovernance,
    expected_document_version: str,
) -> None:
    if (
        not destination.consent_bundle_id
        or destination.consent_bundle_id != governance.current_consent_bundle_id
    ):
        raise StoreReviewerInvitationRebindError(
            "The destination invitation is not bound to the current consent bundle."
        )
    documents = db.execute(
        select(StudyConsentBundleDocument, StudyConsentDocument)
        .join(
            StudyConsentDocument,
            StudyConsentDocument.id == StudyConsentBundleDocument.document_id,
        )
        .where(StudyConsentBundleDocument.bundle_id == destination.consent_bundle_id)
    ).all()
    if (
        len(documents) != len(REQUIRED_DOCUMENT_TYPES)
        or {membership.document_type for membership, _document in documents}
        != REQUIRED_DOCUMENT_TYPES
        or any(
            document.organisation_id != destination.organisation_id
            or document.study_id != destination.study_id
            or document.version != expected_document_version
            for _membership, document in documents
        )
    ):
        raise StoreReviewerInvitationRebindError(
            "The destination consent bundle is incomplete or unexpected."
        )


def _result(
    *,
    participant: Participant,
    credential: ParticipantPasswordCredential,
    source: ParticipantInvitation,
    destination: ParticipantInvitation,
    study: Study,
    credential_before: CredentialSnapshot,
    participant_before: ParticipantSnapshot,
) -> StoreReviewerInvitationRebindResult:
    credential_after = _credential_snapshot(credential)
    participant_after = _participant_snapshot(participant)
    return StoreReviewerInvitationRebindResult(
        participant_id=participant.id,
        credential_id=credential.id,
        source_invitation_id=source.id,
        destination_invitation_id=destination.id,
        organisation_id=participant.organisation_id,
        project_id=study.project_id,
        study_id=study.id,
        destination_bundle_id=destination.consent_bundle_id or 0,
        document_version=APPLE_DOCUMENT_VERSION,
        changed=True,
        participant_unchanged=participant_after == participant_before,
        username_unchanged=(
            credential_after.login_identifier_normalised
            == credential_before.login_identifier_normalised
        ),
        password_unchanged=(
            credential_after.password_hash == credential_before.password_hash
        ),
        scope_unchanged=(
            credential_after.organisation_id == credential_before.organisation_id
            and credential_after.participant_id == credential_before.participant_id
            and source.organisation_id == destination.organisation_id
            and source.participant_id == destination.participant_id
            and source.study_id == destination.study_id
        ),
        consent_unchanged=(
            participant.consent_status == ConsentStatus.pending.value
            and source.accepted_at is None
            and destination.accepted_at is None
        ),
        consent_status=participant.consent_status,
        store_reviewer_designation=bool(participant.is_store_reviewer),
        credential_enabled=bool(credential.enabled),
    )


def _durable_detail(
    correlation_id: str, result: StoreReviewerInvitationRebindResult
) -> str:
    return json.dumps(
        {"correlation_id": correlation_id, "result": result.approved_result()},
        sort_keys=True,
        separators=(",", ":"),
    )


def rebind_store_reviewer_invitation(
    db: Session,
    *,
    participant_id: int,
    source_invitation_id: int,
    destination_invitation_id: int,
    expected_participant_reference: str,
    expected_login_identifier: str,
    expected_organisation_name: str,
    expected_project_title: str,
    expected_study_code: str,
    expected_document_version: str,
    correlation_id: str,
) -> StoreReviewerInvitationRebindResult:
    """Rebind one explicitly designated reviewer after exhaustive scope checks."""
    correlation_id = _validate_correlation_id(correlation_id)
    if (
        type(participant_id) is not int
        or type(source_invitation_id) is not int
        or type(destination_invitation_id) is not int
        or min(participant_id, source_invitation_id, destination_invitation_id) <= 0
        or source_invitation_id == destination_invitation_id
    ):
        raise StoreReviewerInvitationRebindError("The fixed target is invalid.")

    participant = _require_exactly_one(
        list(
            db.scalars(
                select(Participant)
                .where(Participant.id == participant_id)
                .with_for_update()
            )
        ),
        "The reviewer participant could not be established exactly.",
    )
    source = _require_exactly_one(
        list(
            db.scalars(
                select(ParticipantInvitation)
                .where(ParticipantInvitation.id == source_invitation_id)
                .with_for_update()
            )
        ),
        "The source invitation could not be established exactly.",
    )
    destination = _require_exactly_one(
        list(
            db.scalars(
                select(ParticipantInvitation)
                .where(ParticipantInvitation.id == destination_invitation_id)
                .with_for_update()
            )
        ),
        "The destination invitation could not be established exactly.",
    )
    credentials = list(
        db.scalars(
            select(ParticipantPasswordCredential)
            .where(ParticipantPasswordCredential.participant_id == participant.id)
            .with_for_update()
        )
    )
    credential = _require_exactly_one(
        credentials, "The existing reviewer credential could not be established exactly."
    )

    study = db.scalar(
        select(Study)
        .where(Study.id == destination.study_id)
        .with_for_update()
    )
    project = (
        db.scalar(
            select(Project)
            .where(Project.id == study.project_id)
            .with_for_update()
        )
        if study
        else None
    )
    organisation = db.scalar(
        select(Organisation)
        .where(Organisation.id == participant.organisation_id)
        .with_for_update()
    )
    governance = db.scalar(
        select(StudyGovernance)
        .where(StudyGovernance.study_id == destination.study_id)
        .with_for_update()
    )
    if not study or not project or not organisation or not governance:
        raise StoreReviewerInvitationRebindError(
            "The reviewer study scope could not be established exactly."
        )

    if (
        participant.reference != expected_participant_reference
        or participant.is_store_reviewer is not True
        or participant.status != ParticipantStatus.invited.value
        or participant.consent_status != ConsentStatus.pending.value
        or credential.login_identifier_normalised != expected_login_identifier
        or credential.organisation_id != participant.organisation_id
        or not credential.enabled
        or organisation.name != expected_organisation_name
        or project.title != expected_project_title
        or study.code != expected_study_code
    ):
        raise StoreReviewerInvitationRebindError(
            "The reviewer identity is not eligible for the fixed transition."
        )
    if (
        source.organisation_id != participant.organisation_id
        or destination.organisation_id != participant.organisation_id
        or source.participant_id != participant.id
        or destination.participant_id != participant.id
        or source.study_id != destination.study_id
        or destination.study_id != study.id
        or study.organisation_id != participant.organisation_id
        or project.id != study.project_id
        or project.organisation_id != participant.organisation_id
        or governance.organisation_id != participant.organisation_id
    ):
        raise StoreReviewerInvitationRebindError(
            "The source and destination scope does not match exactly."
        )
    if source.revoked_at is None or source.accepted_at is not None:
        raise StoreReviewerInvitationRebindError(
            "The source invitation is not the expected revoked pending invitation."
        )
    now = datetime.now(timezone.utc)
    expiry_now = now if destination.expires_at.tzinfo else now.replace(tzinfo=None)
    if (
        destination.revoked_at is not None
        or destination.accepted_at is not None
        or destination.expires_at <= expiry_now
    ):
        raise StoreReviewerInvitationRebindError(
            "The destination invitation is not pending and eligible."
        )
    enrolments = list(
        db.scalars(
            select(StudyEnrolment)
            .where(
                StudyEnrolment.organisation_id == participant.organisation_id,
                StudyEnrolment.study_id == study.id,
                StudyEnrolment.participant_id == participant.id,
                StudyEnrolment.status != "withdrawn",
            )
            .with_for_update()
        )
    )
    _require_exactly_one(
        enrolments, "The reviewer does not have one active study enrolment."
    )
    live_pending = _eligible_pending_invitations(
        db, participant=participant, study=study, at=now
    )
    if [invitation.id for invitation in live_pending] != [destination.id]:
        raise StoreReviewerInvitationRebindError(
            "The eligible destination invitation is ambiguous."
        )
    _require_current_bundle(
        db,
        destination=destination,
        governance=governance,
        expected_document_version=expected_document_version,
    )

    participant_before = _participant_snapshot(participant)
    credential_before = _credential_snapshot(credential)
    expected_result = _result(
        participant=participant,
        credential=credential,
        source=source,
        destination=destination,
        study=study,
        credential_before=credential_before,
        participant_before=participant_before,
    )
    expected_detail = _durable_detail(correlation_id, expected_result)
    if credential.participant_invitation_id == destination.id:
        completed = list(
            db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.action == REBIND_AUDIT_ACTION,
                    AuditEvent.entity_type == "participant_password_credential",
                    AuditEvent.entity_id == str(credential.id),
                    AuditEvent.detail == expected_detail,
                )
                .with_for_update()
            )
        )
        if len(completed) == 1:
            return expected_result
        raise StoreReviewerInvitationRebindError(
            "The credential is already associated with another operation."
        )
    if credential.participant_invitation_id != source.id:
        raise StoreReviewerInvitationRebindError(
            "The credential is not bound to the expected source invitation."
        )

    changed = db.execute(
        update(ParticipantPasswordCredential)
        .where(
            ParticipantPasswordCredential.id == credential.id,
            ParticipantPasswordCredential.organisation_id == participant.organisation_id,
            ParticipantPasswordCredential.participant_id == participant.id,
            ParticipantPasswordCredential.participant_invitation_id == source.id,
            ParticipantPasswordCredential.login_identifier_normalised
            == expected_login_identifier,
            ParticipantPasswordCredential.password_hash == credential_before.password_hash,
            ParticipantPasswordCredential.enabled.is_(True),
        )
        .values(participant_invitation_id=destination.id)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise StoreReviewerInvitationRebindError(
            "The credential changed before the transition could commit."
        )
    db.expire(credential)
    db.refresh(credential)
    result = _result(
        participant=participant,
        credential=credential,
        source=source,
        destination=destination,
        study=study,
        credential_before=credential_before,
        participant_before=participant_before,
    )
    if (
        credential.participant_invitation_id != destination.id
        or not result.participant_unchanged
        or not result.username_unchanged
        or not result.password_unchanged
        or not result.scope_unchanged
        or not result.consent_unchanged
        or not result.store_reviewer_designation
        or not result.credential_enabled
        or db.new
        or db.dirty
        or db.deleted
    ):
        raise StoreReviewerInvitationRebindError("Post-write verification failed.")

    detail = _durable_detail(correlation_id, result)
    db.add(
        AuditEvent(
            organisation_id=participant.organisation_id,
            project_id=study.project_id,
            study_id=study.id,
            actor_user_id=None,
            action=REBIND_AUDIT_ACTION,
            entity_type="participant_password_credential",
            entity_id=str(credential.id),
            detail=detail,
        )
    )
    db.flush()
    completed = list(
        db.scalars(
            select(AuditEvent).where(
                AuditEvent.action == REBIND_AUDIT_ACTION,
                AuditEvent.entity_type == "participant_password_credential",
                AuditEvent.entity_id == str(credential.id),
                AuditEvent.detail == detail,
            )
        )
    )
    if len(completed) != 1:
        raise StoreReviewerInvitationRebindError(
            "Durable completion verification failed."
        )
    return result


def execute_apple_reviewer_invitation_rebind(
    session_factory: sessionmaker = SessionLocal,
    *,
    correlation_id: str,
) -> StoreReviewerInvitationRebindResult:
    """Run the single approved Apple reviewer rebind transaction."""
    with session_factory.begin() as db:
        return rebind_store_reviewer_invitation(
            db,
            participant_id=APPLE_PARTICIPANT_ID,
            source_invitation_id=APPLE_SOURCE_INVITATION_ID,
            destination_invitation_id=APPLE_DESTINATION_INVITATION_ID,
            expected_participant_reference=APPLE_PARTICIPANT_REFERENCE,
            expected_login_identifier=APPLE_LOGIN_IDENTIFIER,
            expected_organisation_name=APPLE_ORGANISATION_NAME,
            expected_project_title=APPLE_PROJECT_TITLE,
            expected_study_code=APPLE_STUDY_CODE,
            expected_document_version=APPLE_DOCUMENT_VERSION,
            correlation_id=correlation_id,
        )
