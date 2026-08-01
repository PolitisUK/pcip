from datetime import datetime

from app.models import Participant, ParticipantInvitation


def grant_participant_consent(
    invitation: ParticipantInvitation,
    participant: Participant,
    accepted_at: datetime,
) -> None:
    if not invitation.accepted_at:
        invitation.accepted_at = accepted_at
    participant.status = "active"
    participant.consent_status = "granted"
