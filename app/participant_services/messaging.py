from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ParticipantInvitation, ParticipantMessage


def list_participant_visible_messages(
    db: Session,
    *,
    study_id: int,
    participant_id: int,
) -> list[ParticipantMessage]:
    return db.scalars(
        select(ParticipantMessage)
        .where(
            ParticipantMessage.study_id == study_id,
            ParticipantMessage.participant_id == participant_id,
            ParticipantMessage.internal_note == False,
        )
        .order_by(ParticipantMessage.created_at)
    ).all()


def create_participant_message(
    invitation: ParticipantInvitation,
    *,
    body: str,
) -> ParticipantMessage:
    return ParticipantMessage(
        organisation_id=invitation.organisation_id,
        study_id=invitation.study_id,
        participant_id=invitation.participant_id,
        sender_type="participant",
        body=body.strip(),
    )


def create_researcher_message(
    *,
    organisation_id: int,
    study_id: int,
    participant_id: int,
    sender_user_id: int,
    body: str,
    internal_note: bool,
) -> ParticipantMessage:
    return ParticipantMessage(
        organisation_id=organisation_id,
        study_id=study_id,
        participant_id=participant_id,
        sender_type="researcher",
        sender_user_id=sender_user_id,
        body=body.strip(),
        internal_note=internal_note,
    )