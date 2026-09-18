from __future__ import annotations

from datetime import datetime, timedelta, timezone
from inspect import signature

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ParticipantPrivacyRequest, StudyEnrolment, StudyGovernance
from scripts.get_latest_failed_account_deletion_status import (
    execute_get_latest_failed_account_deletion_status,
)


def status_session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def failed_request(
    *,
    organisation_id: int = 10,
    participant_id: int | None = 20,
    requested_at: datetime,
    retry_count: int = 1,
    last_error_code: str = "StorageError",
) -> ParticipantPrivacyRequest:
    return ParticipantPrivacyRequest(
        organisation_id=organisation_id,
        participant_id=participant_id,
        study_id=None,
        request_type="deletion",
        scope="account",
        status="failed_retrying",
        retriable=True,
        retry_count=retry_count,
        last_error_code=last_error_code,
        requested_at=requested_at,
    )


def test_lookup_is_parameterless_and_reports_no_matching_request():
    assert list(
        signature(execute_get_latest_failed_account_deletion_status).parameters
    ) == ["session_factory"]

    result = execute_get_latest_failed_account_deletion_status(status_session_factory())

    assert result.approved_result() == {"found": False}


def test_latest_failed_account_deletion_is_selected_deterministically_and_minimally():
    factory = status_session_factory()
    base = datetime(2026, 9, 18, tzinfo=timezone.utc)
    with factory() as db:
        older = failed_request(
            requested_at=base, retry_count=2, last_error_code="OlderError"
        )
        newer = failed_request(
            requested_at=base + timedelta(seconds=1),
            retry_count=3,
            last_error_code="ObjectStoreFailure",
        )
        db.add_all([older, newer])
        db.commit()
        newer_id = newer.id

    result = execute_get_latest_failed_account_deletion_status(
        factory
    ).approved_result()

    assert result == {
        "privacy_request_id": newer_id,
        "status": "failed_retrying",
        "retriable": True,
        "retry_count": 3,
        "last_error_code": "ObjectStoreFailure",
        "has_deletion_retention_exception": False,
    }
    rendered = str(result)
    assert "participant" not in rendered.lower()
    assert "study" not in rendered.lower()
    assert "email" not in rendered.lower()


def test_latest_failed_account_deletion_uses_id_as_tiebreaker():
    factory = status_session_factory()
    at = datetime(2026, 9, 18, tzinfo=timezone.utc)
    with factory() as db:
        first = failed_request(requested_at=at, last_error_code="FirstFailure")
        second = failed_request(requested_at=at, last_error_code="SecondFailure")
        db.add_all([first, second])
        db.commit()
        second_id = second.id

    result = execute_get_latest_failed_account_deletion_status(
        factory
    ).approved_result()

    assert result["privacy_request_id"] == second_id
    assert result["last_error_code"] == "SecondFailure"


def test_completed_and_study_scoped_deletions_are_ignored():
    factory = status_session_factory()
    base = datetime(2026, 9, 18, tzinfo=timezone.utc)
    with factory() as db:
        db.add_all(
            [
                ParticipantPrivacyRequest(
                    organisation_id=10,
                    participant_id=20,
                    request_type="deletion",
                    scope="account",
                    status="completed",
                    requested_at=base + timedelta(days=2),
                ),
                ParticipantPrivacyRequest(
                    organisation_id=10,
                    participant_id=20,
                    study_id=30,
                    request_type="deletion",
                    scope="study",
                    status="failed_retrying",
                    retriable=True,
                    retry_count=4,
                    last_error_code="IgnoredStudyFailure",
                    requested_at=base + timedelta(days=1),
                ),
                failed_request(requested_at=base, last_error_code="AccountFailure"),
            ]
        )
        db.commit()

    result = execute_get_latest_failed_account_deletion_status(
        factory
    ).approved_result()

    assert result["status"] == "failed_retrying"
    assert result["last_error_code"] == "AccountFailure"


def test_lookup_reports_meaningful_retention_exception_without_exposing_text():
    factory = status_session_factory()
    at = datetime(2026, 9, 18, tzinfo=timezone.utc)
    with factory() as db:
        db.add(failed_request(requested_at=at))
        db.add_all(
            [
                StudyEnrolment(
                    organisation_id=10,
                    study_id=30,
                    participant_id=20,
                    status="withdrawn",
                ),
                StudyGovernance(
                    organisation_id=10,
                    study_id=30,
                    deletion_retention_exception="Documented statutory retention requirement",
                ),
            ]
        )
        db.commit()

    result = execute_get_latest_failed_account_deletion_status(
        factory
    ).approved_result()

    assert result["has_deletion_retention_exception"] is True
    assert "Documented statutory retention requirement" not in str(result)


def test_lookup_ignores_blank_and_none_retention_exceptions():
    factory = status_session_factory()
    at = datetime(2026, 9, 18, tzinfo=timezone.utc)
    with factory() as db:
        db.add(failed_request(requested_at=at))
        db.add_all(
            [
                StudyEnrolment(
                    organisation_id=10,
                    study_id=30,
                    participant_id=20,
                    status="withdrawn",
                ),
                StudyEnrolment(
                    organisation_id=10,
                    study_id=31,
                    participant_id=20,
                    status="withdrawn",
                ),
                StudyGovernance(
                    organisation_id=10,
                    study_id=30,
                    deletion_retention_exception=" none. ",
                ),
                StudyGovernance(
                    organisation_id=10, study_id=31, deletion_retention_exception=""
                ),
            ]
        )
        db.commit()

    result = execute_get_latest_failed_account_deletion_status(
        factory
    ).approved_result()

    assert result["has_deletion_retention_exception"] is False


def test_lookup_handles_missing_participant_link_without_guessing():
    factory = status_session_factory()
    with factory() as db:
        db.add(
            failed_request(
                participant_id=None,
                requested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            )
        )
        db.commit()

    result = execute_get_latest_failed_account_deletion_status(
        factory
    ).approved_result()

    assert result["has_deletion_retention_exception"] is None
