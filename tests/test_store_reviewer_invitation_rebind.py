from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    AuditEvent,
    Organisation,
    Participant,
    ParticipantInvitation,
    ParticipantPasswordCredential,
    Project,
    Study,
    StudyConsentBundle,
    StudyConsentBundleDocument,
    StudyConsentDocument,
    StudyEnrolment,
    StudyGovernance,
    User,
)
from scripts.store_reviewer_invitation_rebind import (
    APPLE_DESTINATION_INVITATION_ID,
    APPLE_DOCUMENT_VERSION,
    APPLE_LOGIN_IDENTIFIER,
    APPLE_ORGANISATION_NAME,
    APPLE_PARTICIPANT_ID,
    APPLE_PARTICIPANT_REFERENCE,
    APPLE_PROJECT_TITLE,
    APPLE_SOURCE_INVITATION_ID,
    APPLE_STUDY_CODE,
    REBIND_AUDIT_ACTION,
    StoreReviewerInvitationRebindError,
    execute_apple_reviewer_invitation_rebind,
    rebind_store_reviewer_invitation,
)


PASSWORD_HASH = "$argon2id$fixed-password-hash-material"


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    _seed_reviewer(factory)
    try:
        yield factory
    finally:
        engine.dispose()


def _seed_reviewer(factory: sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as db:
        organisation = Organisation(id=4, name=APPLE_ORGANISATION_NAME, slug="apple-review")
        user = User(
            id=1,
            organisation_id=4,
            name="Fixed operator",
            email="operator@example.test",
            role="owner",
        )
        project = Project(
            id=4,
            organisation_id=4,
            title=APPLE_PROJECT_TITLE,
            code="APPLE-REVIEW-PROJECT",
            created_by_id=1,
        )
        study = Study(
            id=4,
            organisation_id=4,
            project_id=4,
            title="App Review Study",
            code=APPLE_STUDY_CODE,
            status="live",
            created_by_id=1,
        )
        participant = Participant(
            id=APPLE_PARTICIPANT_ID,
            organisation_id=4,
            reference=APPLE_PARTICIPANT_REFERENCE,
            name="Apple App Reviewer",
            email="apple-review@example.test",
            status="invited",
            consent_status="pending",
            is_store_reviewer=True,
            created_by_id=1,
        )
        old_bundle = StudyConsentBundle(
            id=1,
            organisation_id=4,
            study_id=4,
            bundle_sha256="a" * 64,
        )
        bundle = StudyConsentBundle(
            id=2,
            organisation_id=4,
            study_id=4,
            bundle_sha256="b" * 64,
        )
        governance = StudyGovernance(
            id=4,
            organisation_id=4,
            study_id=4,
            current_consent_bundle_id=2,
        )
        db.add(organisation)
        db.flush()
        db.add(user)
        db.flush()
        db.add(project)
        db.flush()
        db.add(study)
        db.flush()
        db.add_all([participant, old_bundle, bundle])
        db.flush()
        db.add(governance)
        db.flush()
        for offset, document_type in enumerate(
            ("participant_information", "privacy_notice", "consent_text"), start=1
        ):
            document = StudyConsentDocument(
                id=100 + offset,
                organisation_id=4,
                study_id=4,
                document_type=document_type,
                title=document_type,
                version=APPLE_DOCUMENT_VERSION,
                reference=f"APPLE-{offset}",
                effective_date="28 September 2026",
                body=f"approved {document_type}",
                content_sha256=str(offset) * 64,
            )
            db.add(document)
            db.flush()
            db.add(
                StudyConsentBundleDocument(
                    bundle_id=2,
                    document_id=document.id,
                    document_type=document_type,
                )
            )
        db.add(
            StudyEnrolment(
                organisation_id=4,
                study_id=4,
                participant_id=APPLE_PARTICIPANT_ID,
                status="enrolled",
            )
        )
        db.add_all(
            [
                ParticipantInvitation(
                    id=APPLE_SOURCE_INVITATION_ID,
                    organisation_id=4,
                    participant_id=APPLE_PARTICIPANT_ID,
                    study_id=4,
                    token_hash="source-token-hash",
                    expires_at=now + timedelta(days=1),
                    revoked_at=now,
                    consent_bundle_id=1,
                    invited_by_id=1,
                ),
                ParticipantInvitation(
                    id=APPLE_DESTINATION_INVITATION_ID,
                    organisation_id=4,
                    participant_id=APPLE_PARTICIPANT_ID,
                    study_id=4,
                    token_hash="destination-token-hash",
                    expires_at=now + timedelta(days=30),
                    consent_bundle_id=2,
                    participant_information_version=APPLE_DOCUMENT_VERSION,
                    privacy_notice_version=APPLE_DOCUMENT_VERSION,
                    consent_text_version=APPLE_DOCUMENT_VERSION,
                    invited_by_id=1,
                ),
            ]
        )
        db.flush()
        db.add(
            ParticipantPasswordCredential(
                id=2,
                organisation_id=4,
                participant_id=APPLE_PARTICIPANT_ID,
                participant_invitation_id=APPLE_SOURCE_INVITATION_ID,
                login_identifier_normalised=APPLE_LOGIN_IDENTIFIER,
                password_hash=PASSWORD_HASH,
                enabled=True,
                rotated_at=now - timedelta(days=6),
            )
        )


def _call(db: Session, **overrides):
    values = {
        "participant_id": APPLE_PARTICIPANT_ID,
        "source_invitation_id": APPLE_SOURCE_INVITATION_ID,
        "destination_invitation_id": APPLE_DESTINATION_INVITATION_ID,
        "expected_participant_reference": APPLE_PARTICIPANT_REFERENCE,
        "expected_login_identifier": APPLE_LOGIN_IDENTIFIER,
        "expected_organisation_name": APPLE_ORGANISATION_NAME,
        "expected_project_title": APPLE_PROJECT_TITLE,
        "expected_study_code": APPLE_STUDY_CODE,
        "expected_document_version": APPLE_DOCUMENT_VERSION,
        "correlation_id": str(uuid4()),
    }
    values.update(overrides)
    return rebind_store_reviewer_invitation(db, **values)


def test_fixed_rebind_preserves_credential_identity_password_participant_and_consent(
    session_factory,
):
    with session_factory.begin() as db:
        credential = db.get(ParticipantPasswordCredential, 2)
        participant = db.get(Participant, APPLE_PARTICIPANT_ID)
        before = {
            "username": credential.login_identifier_normalised,
            "password_hash": credential.password_hash,
            "rotated_at": credential.rotated_at,
            "participant": tuple(participant.__dict__.get(key) for key in (
                "id", "organisation_id", "reference", "name", "status",
                "consent_status", "is_store_reviewer", "updated_at",
            )),
        }
        result = _call(db)

        assert credential.participant_invitation_id == APPLE_DESTINATION_INVITATION_ID
        assert credential.login_identifier_normalised == before["username"]
        assert credential.password_hash == before["password_hash"]
        assert credential.rotated_at == before["rotated_at"]
        assert tuple(participant.__dict__.get(key) for key in (
            "id", "organisation_id", "reference", "name", "status",
            "consent_status", "is_store_reviewer", "updated_at",
        )) == before["participant"]
        assert participant.consent_status == "pending"
        assert result.username_unchanged is True
        assert result.password_unchanged is True
        assert result.participant_unchanged is True
        assert result.scope_unchanged is True
        assert result.consent_unchanged is True


def test_fixed_executor_targets_only_apple_reviewer_and_is_idempotent_for_same_correlation(
    session_factory,
):
    correlation_id = str(uuid4())
    first = execute_apple_reviewer_invitation_rebind(
        session_factory, correlation_id=correlation_id
    )
    second = execute_apple_reviewer_invitation_rebind(
        session_factory, correlation_id=correlation_id
    )
    assert first == second
    with session_factory() as db:
        assert db.scalar(
            select(ParticipantPasswordCredential.participant_invitation_id).where(
                ParticipantPasswordCredential.id == 2
            )
        ) == APPLE_DESTINATION_INVITATION_ID
        assert len(list(db.scalars(select(AuditEvent).where(
            AuditEvent.action == REBIND_AUDIT_ACTION
        )))) == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda db: setattr(db.get(ParticipantInvitation, 11), "accepted_at", datetime.now(timezone.utc)),
        lambda db: setattr(db.get(ParticipantInvitation, 11), "revoked_at", datetime.now(timezone.utc)),
        lambda db: setattr(db.get(ParticipantInvitation, 11), "expires_at", datetime.now(timezone.utc) - timedelta(seconds=1)),
        lambda db: setattr(db.get(ParticipantInvitation, 11), "consent_bundle_id", 1),
        lambda db: setattr(db.get(StudyGovernance, 4), "current_consent_bundle_id", 1),
        lambda db: setattr(db.get(Participant, 36), "consent_status", "granted"),
    ],
)
def test_destination_must_be_pending_eligible_and_bound_to_current_bundle(
    session_factory, mutate
):
    with session_factory.begin() as db:
        mutate(db)
        db.flush()
        with pytest.raises(StoreReviewerInvitationRebindError):
            _call(db)


def test_ambiguous_pending_destination_is_rejected(session_factory):
    with session_factory.begin() as db:
        destination = db.get(ParticipantInvitation, 11)
        db.add(
            ParticipantInvitation(
                id=12,
                organisation_id=4,
                participant_id=36,
                study_id=4,
                token_hash="ambiguous-token-hash",
                expires_at=destination.expires_at,
                consent_bundle_id=2,
                invited_by_id=1,
            )
        )
        db.flush()
        with pytest.raises(StoreReviewerInvitationRebindError):
            _call(db)


def test_cross_tenant_destination_is_rejected(session_factory):
    with session_factory.begin() as db:
        db.add(Organisation(id=5, name="Other organisation", slug="other"))
        db.flush()
        db.get(ParticipantInvitation, 11).organisation_id = 5
        db.flush()
        with pytest.raises(StoreReviewerInvitationRebindError):
            _call(db)


def test_cross_participant_destination_is_rejected(session_factory):
    with session_factory.begin() as db:
        db.add(
            Participant(
                id=37,
                organisation_id=4,
                reference="OTHER-REVIEWER",
                name="Other Reviewer",
                status="invited",
                consent_status="pending",
                is_store_reviewer=True,
                created_by_id=1,
            )
        )
        db.flush()
        db.get(ParticipantInvitation, 11).participant_id = 37
        db.flush()
        with pytest.raises(StoreReviewerInvitationRebindError):
            _call(db)


def test_cross_study_destination_is_rejected(session_factory):
    with session_factory.begin() as db:
        db.add(
            Study(
                id=5,
                organisation_id=4,
                project_id=4,
                title="Other study",
                code="OTHER-STUDY",
                created_by_id=1,
            )
        )
        db.flush()
        db.get(ParticipantInvitation, 11).study_id = 5
        db.flush()
        with pytest.raises(StoreReviewerInvitationRebindError):
            _call(db)


def test_ordinary_participant_is_rejected(session_factory):
    with session_factory.begin() as db:
        db.get(Participant, 36).is_store_reviewer = False
        db.flush()
        with pytest.raises(StoreReviewerInvitationRebindError):
            _call(db)


def test_audit_and_approved_result_expose_no_password_or_hash(session_factory):
    with session_factory.begin() as db:
        result = _call(db)
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == REBIND_AUDIT_ACTION))
        assert audit is not None
        rendered = json.dumps(result.approved_result(), sort_keys=True) + audit.detail
        assert PASSWORD_HASH not in rendered
        assert '"password_hash":' not in rendered
        assert "plaintext" not in rendered
        assert json.loads(audit.detail)["result"]["password_unchanged"] is True
