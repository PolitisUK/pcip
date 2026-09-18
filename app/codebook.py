"""Small, explicit codebook operations for researcher-led qualitative analysis."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ResearchCode, Study, User, utcnow


def _clean_name(name: str) -> str:
    value = name.strip()
    if len(value) < 1 or len(value) > 200:
        raise ValueError("Code name must be between 1 and 200 characters")
    return value


def parent_for_code(db: Session, code: ResearchCode, parent_code_id: int | None) -> ResearchCode | None:
    if parent_code_id is None:
        return None
    parent = db.scalar(select(ResearchCode).where(ResearchCode.id == parent_code_id))
    if parent is None:
        raise ValueError("Parent code is unavailable")
    if parent.id == code.id:
        raise ValueError("A code cannot be its own parent")
    if parent.organisation_id != code.organisation_id or parent.study_id != code.study_id:
        raise ValueError("Parent code is outside this study")
    if parent.archived_at is not None:
        raise ValueError("An archived code cannot be used as a parent")
    ancestor = parent
    seen: set[int] = set()
    while True:
        if ancestor.id == code.id:
            raise ValueError("A code cannot be moved into its own hierarchy")
        if ancestor.id in seen:
            raise ValueError("Parent hierarchy is invalid")
        seen.add(ancestor.id)
        if ancestor.parent_code_id is None:
            break
        ancestor = db.get(ResearchCode, ancestor.parent_code_id)
        if ancestor is None:
            raise ValueError("Parent hierarchy is invalid")
    return parent


def create_code(db: Session, user: User, study: Study, *, name: str, definition: str, parent_code_id: int | None) -> ResearchCode:
    row = ResearchCode(
        organisation_id=user.organisation_id,
        study_id=study.id,
        name=_clean_name(name),
        definition=definition.strip(),
        created_by_id=user.id,
    )
    parent_for_code(db, row, parent_code_id)
    row.parent_code_id = parent_code_id
    db.add(row)
    return row


def update_code(db: Session, code: ResearchCode, *, name: str, definition: str, parent_code_id: int | None) -> bool:
    if code.archived_at is not None:
        raise ValueError("Restore an archived code before editing or moving it")
    parent_for_code(db, code, parent_code_id)
    hierarchy_changed = code.parent_code_id != parent_code_id
    code.name = _clean_name(name)
    code.definition = definition.strip()
    code.parent_code_id = parent_code_id
    return hierarchy_changed


def archive_code(code: ResearchCode, user: User) -> None:
    if code.archived_at is None:
        code.archived_at = utcnow()
        code.archived_by_id = user.id


def restore_code(code: ResearchCode) -> None:
    code.archived_at = None
    code.archived_by_id = None
