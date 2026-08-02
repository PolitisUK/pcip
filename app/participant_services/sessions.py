from sqlalchemy.orm import Session

from app.models import ParticipantInvitation, PublicAuthSession


def resolve_participant_invitation(
    db: Session,
    session_row: PublicAuthSession | None,
) -> ParticipantInvitation | None:
    """Resolve the invitation referenced by an already-authenticated public session."""

    if not session_row or session_row.participant_invitation_id is None:
        return None
    return db.get(ParticipantInvitation, session_row.participant_invitation_id)
