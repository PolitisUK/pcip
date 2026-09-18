"""Return minimal status for the latest retryable account-deletion failure.

This is an implementation detail of the protected production-operations
worker.  It accepts no caller-controlled identifiers or query input, runs in a
read-only transaction, and deliberately returns no participant, study, or
retention-exception content.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import ParticipantPrivacyRequest, StudyEnrolment, StudyGovernance


class FailedAccountDeletionStatusLookupError(RuntimeError):
    """Raised when the fixed lookup cannot establish a safe minimal result."""


@dataclass(frozen=True)
class NoFailedAccountDeletion:
    found: bool = False

    def approved_result(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class FailedAccountDeletionStatus:
    privacy_request_id: int
    status: str
    retriable: bool
    retry_count: int
    last_error_code: str
    has_deletion_retention_exception: bool | None

    def approved_result(self) -> dict[str, int | str | bool | None]:
        return asdict(self)


def _meaningful_retention_exception(value: str | None) -> bool:
    return isinstance(value, str) and value.strip().lower() not in {"", "none", "none."}


def _has_deletion_retention_exception(
    db: Session,
    *,
    organisation_id: int,
    participant_id: int,
) -> bool:
    """Check linked-study governance internally without returning it."""
    values = db.scalars(
        select(StudyGovernance.deletion_retention_exception)
        .join(
            StudyEnrolment,
            and_(
                StudyEnrolment.organisation_id == StudyGovernance.organisation_id,
                StudyEnrolment.study_id == StudyGovernance.study_id,
            ),
        )
        .where(
            StudyEnrolment.organisation_id == organisation_id,
            StudyEnrolment.participant_id == participant_id,
        )
    )
    return any(_meaningful_retention_exception(value) for value in values)


def get_latest_failed_account_deletion_status(
    db: Session,
) -> NoFailedAccountDeletion | FailedAccountDeletionStatus:
    """Select the latest failed account deletion using fixed lifecycle criteria."""
    request = db.scalar(
        select(ParticipantPrivacyRequest)
        .where(
            ParticipantPrivacyRequest.scope == "account",
            ParticipantPrivacyRequest.request_type == "deletion",
            ParticipantPrivacyRequest.status == "failed_retrying",
        )
        .order_by(
            ParticipantPrivacyRequest.requested_at.desc(),
            ParticipantPrivacyRequest.id.desc(),
        )
        .limit(1)
    )
    if request is None:
        return NoFailedAccountDeletion()
    if (
        not isinstance(request.id, int)
        or request.id <= 0
        or request.status != "failed_retrying"
        or type(request.retriable) is not bool
        or not isinstance(request.retry_count, int)
        or request.retry_count < 0
        or not isinstance(request.last_error_code, str)
        or len(request.last_error_code) > 80
    ):
        raise FailedAccountDeletionStatusLookupError(
            "The deletion status is malformed."
        )

    has_exception = (
        None
        if request.participant_id is None
        else _has_deletion_retention_exception(
            db,
            organisation_id=request.organisation_id,
            participant_id=request.participant_id,
        )
    )
    if db.new or db.dirty or db.deleted:
        raise FailedAccountDeletionStatusLookupError(
            "Read-only lookup detected pending changes."
        )
    return FailedAccountDeletionStatus(
        privacy_request_id=request.id,
        status=request.status,
        retriable=request.retriable,
        retry_count=request.retry_count,
        last_error_code=request.last_error_code,
        has_deletion_retention_exception=has_exception,
    )


def execute_get_latest_failed_account_deletion_status(
    session_factory: sessionmaker = SessionLocal,
) -> NoFailedAccountDeletion | FailedAccountDeletionStatus:
    """Run the fixed lookup in a read-only transaction and always roll back."""
    db = session_factory()
    try:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        return get_latest_failed_account_deletion_status(db)
    finally:
        db.rollback()
        db.close()
