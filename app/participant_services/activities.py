from datetime import datetime, timedelta, timezone

from app.models import Activity, Study


def activity_window(
    study_row: Study,
    activity_row: Activity,
    current_time: datetime | None = None,
) -> dict[str, datetime | str | None]:
    """Return the server-authoritative availability window for an activity."""

    if not study_row.start_at:
        return {
            "status": "open",
            "release_at": None,
            "due_at": None,
        }

    start_at = study_row.start_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)

    current = current_time or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    release_at = start_at + timedelta(
        days=max(0, int(activity_row.release_offset_days or 0))
    )
    due_at = (
        start_at + timedelta(days=int(activity_row.due_offset_days))
        if activity_row.due_offset_days is not None
        else None
    )

    if current < release_at:
        status = "upcoming"
    elif due_at and current > due_at:
        status = "closed"
    else:
        status = "open"

    return {
        "status": status,
        "release_at": release_at,
        "due_at": due_at,
    }
