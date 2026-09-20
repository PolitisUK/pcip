"""Researcher-authored finding lifecycle services."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analysis_objects import analytical_study_permission
from .models import ResearchFinding, Study, User

MAX_FINDING_BODY = 30000


def finding_study_access(db: Session, user: User, study_id: int) -> tuple[Study, str]:
    study = db.scalar(
        select(Study).where(
            Study.id == study_id,
            Study.organisation_id == user.organisation_id,
        )
    )
    permission = analytical_study_permission(db, user, study) if study else None
    if study is None or permission is None:
        raise PermissionError("Research findings are unavailable")
    return study, permission


def finding_text(title: str, body: str) -> tuple[str, str]:
    clean_title = " ".join((title or "").split())
    clean_body = (body or "").strip()
    if len(clean_title) < 3:
        raise ValueError("Finding title must contain at least 3 characters")
    if len(clean_title) > 200:
        raise ValueError("Finding title must contain 200 characters or fewer")
    if not clean_body:
        raise ValueError("Finding text is required")
    if len(clean_body) > MAX_FINDING_BODY:
        raise ValueError("Finding text must contain 30,000 characters or fewer")
    return clean_title, clean_body


def changeable_finding(
    db: Session, user: User, *, study_id: int, finding_id: int
) -> ResearchFinding:
    _, permission = finding_study_access(db, user, study_id)
    if permission not in {"edit", "manage"}:
        raise PermissionError("Finding is unavailable")
    row = db.scalar(
        select(ResearchFinding).where(
            ResearchFinding.id == finding_id,
            ResearchFinding.organisation_id == user.organisation_id,
            ResearchFinding.study_id == study_id,
        )
    )
    if row is None:
        raise ValueError("Finding is unavailable")
    if row.created_by_id != user.id and permission != "manage":
        raise PermissionError("You cannot change this finding")
    return row
