"""Researcher-controlled theme creation with reviewed evidence traceability."""

import json

from sqlalchemy import select

from .models import ResearchCode, ResearchTheme, ResearchThemeCode, utcnow


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


def update_theme(theme: ResearchTheme, *, name: str, description: str) -> None:
    if theme.archived_at is not None:
        raise ValueError("Restore an archived theme before refining it")
    cleaned_name = name.strip()
    if len(cleaned_name) < 3 or len(cleaned_name) > 200:
        raise ValueError("Theme name must be between 3 and 200 characters")
    theme.name = cleaned_name
    theme.description = description.strip()


def archive_theme(theme: ResearchTheme, user) -> None:
    if theme.archived_at is None:
        theme.archived_at = utcnow()
        theme.archived_by_id = user.id


def restore_theme(theme: ResearchTheme) -> None:
    theme.archived_at = None
    theme.archived_by_id = None


def link_code(db, user, theme: ResearchTheme, code: ResearchCode) -> ResearchThemeCode:
    if theme.archived_at is not None:
        raise ValueError("Restore an archived theme before linking codes")
    if code.archived_at is not None:
        raise ValueError("Archived codes cannot be newly linked")
    if code.organisation_id != theme.organisation_id or code.study_id != theme.study_id:
        raise ValueError("Code is outside this theme's study")
    existing = db.scalar(select(ResearchThemeCode).where(
        ResearchThemeCode.research_theme_id == theme.id,
        ResearchThemeCode.research_code_id == code.id,
    ))
    if existing:
        return existing
    row = ResearchThemeCode(
        organisation_id=theme.organisation_id,
        study_id=theme.study_id,
        research_theme_id=theme.id,
        research_code_id=code.id,
        linked_by_id=user.id,
    )
    db.add(row)
    return row
