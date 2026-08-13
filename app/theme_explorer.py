"""Researcher-controlled theme creation with reviewed evidence traceability."""

import json

from .models import ResearchTheme


def parse_suggestion_ids(value: str) -> set[int]:
    try:
        identifiers = {int(item) for item in value.split(",") if item.strip()}
    except ValueError as exc:
        raise ValueError("Source analysis IDs must be whole numbers") from exc
    if not identifiers:
        raise ValueError("Select at least one reviewed source analysis")
    return identifiers


def create_theme(db, user, study, *, name: str, description: str, suggestions):
    if user.role not in {"owner", "admin", "researcher"}:
        raise PermissionError("Only researchers can create themes")
    cleaned_name = name.strip()
    if len(cleaned_name) < 3:
        raise ValueError("Theme name must be at least 3 characters")
    if not suggestions:
        raise ValueError("Select at least one reviewed source analysis")
    if any(
        row.organisation_id != user.organisation_id
        or row.study_id != study.id
        or row.status != "accepted"
        for row in suggestions
    ):
        raise PermissionError("Themes can only use accepted analysis from this study")
    row = ResearchTheme(
        organisation_id=user.organisation_id,
        study_id=study.id,
        name=cleaned_name,
        description=description.strip(),
        source_suggestion_ids_json=json.dumps(sorted(row.id for row in suggestions)),
        status="researcher_draft",
        created_by_id=user.id,
    )
    db.add(row)
    return row
