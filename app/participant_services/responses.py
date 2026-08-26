import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityResponse


def resolve_activity_response(
    db: Session,
    activity_id: int,
    participant_id: int,
    client_entry_key_hash: str | None = None,
) -> ActivityResponse | None:
    statement = select(ActivityResponse).where(
        ActivityResponse.activity_id == activity_id,
        ActivityResponse.participant_id == participant_id,
    )
    if client_entry_key_hash:
        statement = statement.where(ActivityResponse.client_entry_key_hash == client_entry_key_hash)
    return db.scalar(statement.order_by(ActivityResponse.id.desc()))


def resolve_or_create_activity_response(
    db: Session,
    organisation_id: int,
    study_id: int,
    activity_id: int,
    participant_id: int,
    *,
    repeatable: bool = False,
    client_entry_key_hash: str | None = None,
) -> ActivityResponse:
    # A repeatable activity creates a new immutable response context for each
    # entry.  The same client key resolves to that exact context on retry.
    response = resolve_activity_response(
        db, activity_id, participant_id,
        client_entry_key_hash if repeatable else None,
    ) if (not repeatable or client_entry_key_hash) else None
    if response:
        return response
    response = ActivityResponse(
        organisation_id=organisation_id,
        study_id=study_id,
        activity_id=activity_id,
        participant_id=participant_id,
        repeatable=repeatable,
        client_entry_key_hash=client_entry_key_hash,
    )
    db.add(response)
    db.flush()
    return response


def serialise_response_payload(answer: str, choices: str | list[str]) -> tuple[dict[str, object], list[str]]:
    raw_choices = choices.split("|") if isinstance(choices, str) else choices
    choice_list = [x.strip() for x in raw_choices if isinstance(x, str) and x.strip()]
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
