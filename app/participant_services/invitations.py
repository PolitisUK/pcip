from datetime import datetime
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Participant, ParticipantInvitation, Study, StudyEnrolment
from app.security import new_token, token_hash


def resolve_invitation_by_token(db: Session, raw_token: str) -> ParticipantInvitation | None:
    if not raw_token:
        return None
    return db.scalar(
        select(ParticipantInvitation).where(
            ParticipantInvitation.token_hash == token_hash(raw_token)
        )
    )


class LiveParticipantInvitationConflict(Exception):
    """Raised when an invitation would violate the live invitation invariant.

    The exception deliberately carries no participant or token information so
    callers can safely turn it into an administrator-facing error.
    """


def _live_invitation_statement(
    *,
    organisation_id: int,
    study_id: int,
    participant_id: int,
    current_time: datetime,
    exclude_invitation_id: int | None = None,
):
    statement = select(ParticipantInvitation).where(
        ParticipantInvitation.organisation_id == organisation_id,
        ParticipantInvitation.study_id == study_id,
        ParticipantInvitation.participant_id == participant_id,
        ParticipantInvitation.revoked_at.is_(None),
        ParticipantInvitation.expires_at > current_time,
    )
    if exclude_invitation_id is not None:
        statement = statement.where(ParticipantInvitation.id != exclude_invitation_id)
    return statement.order_by(ParticipantInvitation.id.asc())


def lock_participant_invitation_scope(
    db: Session,
    *,
    organisation_id: int,
    participant_id: int,
) -> None:
    """Serialize invitation changes for one participant within an organisation.

    PostgreSQL locks the stable participant row for the duration of the
    transaction.  That also covers the otherwise difficult "no rows yet"
    creation race, unlike locking invitation rows alone.  SQLite ignores
    ``FOR UPDATE`` but remains suitable for the repository's unit tests.
    """

    participant = db.scalar(
        participant_invitation_scope_lock_statement(
            organisation_id=organisation_id,
            participant_id=participant_id,
        )
    )
    if participant is None:
        raise ValueError("Participant is outside the invitation organisation scope.")


def participant_invitation_scope_lock_statement(
    *,
    organisation_id: int,
    participant_id: int,
):
    """The PostgreSQL lock statement used to serialize invitation changes."""

    return (
        select(Participant)
        .where(
            Participant.id == participant_id,
            Participant.organisation_id == organisation_id,
        )
        .with_for_update()
    )


def find_live_invitations(
    db: Session,
    *,
    organisation_id: int,
    study_id: int,
    participant_id: int,
    current_time: datetime,
    exclude_invitation_id: int | None = None,
) -> list[ParticipantInvitation]:
    """Return all unrevoked, unexpired invitations, regardless of acceptance."""

    return list(
        db.scalars(
            _live_invitation_statement(
                organisation_id=organisation_id,
                study_id=study_id,
                participant_id=participant_id,
                current_time=current_time,
                exclude_invitation_id=exclude_invitation_id,
            )
        )
    )


def find_live_unaccepted_invitation(
    db: Session,
    study_id: int,
    participant_id: int,
    current_time: datetime,
) -> ParticipantInvitation | None:
    return db.scalar(
        select(ParticipantInvitation).where(
            ParticipantInvitation.study_id == study_id,
            ParticipantInvitation.participant_id == participant_id,
            ParticipantInvitation.accepted_at.is_(None),
            ParticipantInvitation.revoked_at.is_(None),
            ParticipantInvitation.expires_at > current_time,
        )
    )


def resolve_org_scoped_invitation(
    db: Session,
    organisation_id: int,
    invitation_id: int,
) -> ParticipantInvitation | None:
    return db.scalar(
        select(ParticipantInvitation).where(
            ParticipantInvitation.id == invitation_id,
            ParticipantInvitation.organisation_id == organisation_id,
        )
    )


def create_participant_invitation(
    db: Session,
    organisation_id: int,
    participant_id: int,
    study_id: int,
    invited_by_id: int,
    expires_at: datetime,
) -> tuple[ParticipantInvitation, str]:
    """Create the sole live invitation for a participant and study.

    Callers must retain the surrounding transaction until related consent
    binding, email queueing and audit work have completed.  The participant-row
    lock makes the check-and-create sequence safe for concurrent PostgreSQL
    requests.
    """
    current_time = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()
    lock_participant_invitation_scope(
        db,
        organisation_id=organisation_id,
        participant_id=participant_id,
    )
    # A caller such as the explicit Re-send path may have just revoked the
    # previous invitation in this transaction.  Flush before querying so the
    # shared guard observes that deliberate supersession.
    db.flush()
    if find_live_invitations(
        db,
        organisation_id=organisation_id,
        study_id=study_id,
        participant_id=participant_id,
        current_time=current_time,
    ):
        raise LiveParticipantInvitationConflict()
    raw = new_token()
    invitation = ParticipantInvitation(
        organisation_id=organisation_id,
        participant_id=participant_id,
        study_id=study_id,
        token_hash=token_hash(raw),
        expires_at=expires_at,
        invited_by_id=invited_by_id,
    )
    db.add(invitation)
    db.flush()
    return invitation, raw


def mark_invitation_revoked(invitation: ParticipantInvitation, revoked_at: datetime) -> None:
    invitation.revoked_at = revoked_at


def ensure_invitation_can_be_accepted(
    db: Session,
    invitation: ParticipantInvitation,
    current_time: datetime,
) -> None:
    """Fail closed if accepting would leave another live invitation in scope."""

    lock_participant_invitation_scope(
        db,
        organisation_id=invitation.organisation_id,
        participant_id=invitation.participant_id,
    )
    db.refresh(invitation)
    # SQLite returns naive datetimes even for timezone-aware columns, while
    # PostgreSQL preserves the offset.  Compare their UTC wall-clock values;
    # all application timestamps are generated in UTC.
    if invitation.revoked_at or (
        invitation.expires_at.replace(tzinfo=None)
        <= current_time.replace(tzinfo=None)
    ):
        raise LiveParticipantInvitationConflict()
    if find_live_invitations(
        db,
        organisation_id=invitation.organisation_id,
        study_id=invitation.study_id,
        participant_id=invitation.participant_id,
        current_time=current_time,
        exclude_invitation_id=invitation.id,
    ):
        raise LiveParticipantInvitationConflict()


def duplicate_live_accepted_invitation_groups(
    db: Session,
    current_time: datetime,
):
    """Return the minimum platform-administration data for invalid groups."""

    return db.execute(
        select(
            ParticipantInvitation.organisation_id,
            ParticipantInvitation.participant_id,
            ParticipantInvitation.study_id,
            Study.title.label("study_title"),
            func.count(ParticipantInvitation.id).label("invitation_count"),
        )
        .join(Study, Study.id == ParticipantInvitation.study_id)
        .where(
            ParticipantInvitation.accepted_at.is_not(None),
            ParticipantInvitation.revoked_at.is_(None),
            ParticipantInvitation.expires_at > current_time,
        )
        .group_by(
            ParticipantInvitation.organisation_id,
            ParticipantInvitation.participant_id,
            ParticipantInvitation.study_id,
            Study.title,
        )
        .having(func.count(ParticipantInvitation.id) > 1)
        .order_by(
            ParticipantInvitation.organisation_id,
            ParticipantInvitation.participant_id,
            ParticipantInvitation.study_id,
        )
    ).all()


def duplicate_live_accepted_invitations(
    db: Session,
    *,
    organisation_id: int,
    participant_id: int,
    study_id: int,
    current_time: datetime,
    lock: bool = False,
) -> list[ParticipantInvitation]:
    statement = (
        _live_invitation_statement(
            organisation_id=organisation_id,
            participant_id=participant_id,
            study_id=study_id,
            current_time=current_time,
        )
        .where(ParticipantInvitation.accepted_at.is_not(None))
    )
    if lock:
        statement = statement.with_for_update()
    return list(db.scalars(statement))


def duplicate_invitation_review_fingerprint(
    invitations: list[ParticipantInvitation],
) -> str:
    """Detect a change between review and explicit confirmation without PII."""

    material = "|".join(
        f"{row.id}:{row.created_at.isoformat()}:{row.accepted_at.isoformat()}:{row.revoked_at}:{row.expires_at.isoformat()}"
        for row in invitations
    )
    return sha256(material.encode("utf-8")).hexdigest()


def invitation_enrolment(
    db: Session,
    *,
    organisation_id: int,
    participant_id: int,
    study_id: int,
) -> StudyEnrolment | None:
    return db.scalar(
        select(StudyEnrolment).where(
            StudyEnrolment.organisation_id == organisation_id,
            StudyEnrolment.participant_id == participant_id,
            StudyEnrolment.study_id == study_id,
        )
    )
