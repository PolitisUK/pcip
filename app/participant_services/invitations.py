from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ParticipantInvitation
from app.security import new_token, token_hash


def resolve_invitation_by_token(db: Session, raw_token: str) -> ParticipantInvitation | None:
    if not raw_token:
        return None
    return db.scalar(
        select(ParticipantInvitation).where(
            ParticipantInvitation.token_hash == token_hash(raw_token)
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