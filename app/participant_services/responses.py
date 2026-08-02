import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityResponse


def resolve_activity_response(
    db: Session,
    activity_id: int,
    participant_id: int,
) -> ActivityResponse | None:
    return db.scalar(
        select(ActivityResponse).where(
            ActivityResponse.activity_id == activity_id,
            ActivityResponse.participant_id == participant_id,
        )
    )


def resolve_or_create_activity_response(
    db: Session,
    organisation_id: int,
    study_id: int,
    activity_id: int,
    participant_id: int,
) -> ActivityResponse:
    response = resolve_activity_response(db, activity_id, participant_id)
    if response:
        return response
    response = ActivityResponse(
        organisation_id=organisation_id,
        study_id=study_id,
        activity_id=activity_id,
        participant_id=participant_id,
    )
    db.add(response)
    db.flush()
    return response


def serialise_response_payload(answer: str, choices: str) -> tuple[dict[str, object], list[str]]:
    choice_list = [x.strip() for x in choices.split("|") if x.strip()]
    value = {"answer": answer, "choices": choice_list}
    return value, choice_list


def apply_response_action(
    response: ActivityResponse,
    value: dict[str, object],
    action: str,
    current_time: datetime,
) -> None:
    response.value_json = json.dumps(value)
    response.status = "submitted" if action == "submit" else "draft"
    response.submitted_at = current_time if action == "submit" else None