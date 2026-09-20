"""Safe, typed resolution of existing Analysis Workbench objects.

This module is deliberately an allow-list, not a generic model resolver.  It is
the internal object contract used by relationships, canvases and later
traceability views.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AnalysisTarget,
    AnalyticalRelationship,
    CodeApplication,
    Participant,
    ResearchAnnotation,
    ResearchCode,
    ResearchMemo,
    ResearchTheme,
    Study,
    StudyAccess,
    StudyEnrolment,
    User,
)

ANALYTICAL_OBJECT_TYPES = frozenset(
    {
        "analysis_target",
        "code_application",
        "annotation",
        "memo",
        "code",
        "theme",
        "relationship",
        "participant_case",
    }
)


@dataclass(frozen=True)
class AnalyticalObjectSummary:
    object_type: str
    object_id: int
    organisation_id: int
    study_id: int
    label: str
    summary: str
    navigation_url: str | None
    editable: bool


def _bounded(value: str, limit: int = 160) -> str:
    cleaned = " ".join((value or "").split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1]}…"


def analytical_study_permission(db: Session, user: User, study: Study) -> str | None:
    """Resolve the existing study access policy without importing web handlers."""
    if study.organisation_id != user.organisation_id:
        return None
    if user.role in {"owner", "admin"}:
        return "manage"
    if study.created_by_id == user.id:
        return "edit"
    access = db.scalar(
        select(StudyAccess).where(
            StudyAccess.study_id == study.id,
            StudyAccess.user_id == user.id,
            StudyAccess.organisation_id == user.organisation_id,
        )
    )
    if access:
        return access.permission
    return "view" if user.role == "observer" else None


def resolve_analytical_object(
    db: Session,
    user: User,
    *,
    study_id: int,
    object_type: str,
    object_id: int,
    require_edit: bool = False,
) -> AnalyticalObjectSummary | None:
    """Resolve one explicitly supported object inside the caller's tenant/study."""
    if object_type not in ANALYTICAL_OBJECT_TYPES or object_id < 1:
        return None
    study = db.scalar(
        select(Study).where(
            Study.id == study_id,
            Study.organisation_id == user.organisation_id,
        )
    )
    permission = analytical_study_permission(db, user, study) if study else None
    if permission is None or (require_edit and permission not in {"edit", "manage"}):
        return None
    model = {
        "analysis_target": AnalysisTarget,
        "code_application": CodeApplication,
        "annotation": ResearchAnnotation,
        "memo": ResearchMemo,
        "code": ResearchCode,
        "theme": ResearchTheme,
        "relationship": AnalyticalRelationship,
    }.get(object_type)
    if model is not None:
        row = db.scalar(
            select(model).where(
                model.id == object_id,
                model.organisation_id == user.organisation_id,
                model.study_id == study_id,
            )
        )
    else:
        row = db.scalar(
            select(Participant)
            .join(StudyEnrolment, StudyEnrolment.participant_id == Participant.id)
            .where(
                Participant.id == object_id,
                Participant.organisation_id == user.organisation_id,
                StudyEnrolment.organisation_id == user.organisation_id,
                StudyEnrolment.study_id == study_id,
            )
        )
    if row is None:
        return None
    label, summary, url = _describe(object_type, row, study)
    return AnalyticalObjectSummary(
        object_type=object_type,
        object_id=row.id,
        organisation_id=user.organisation_id,
        study_id=study_id,
        label=label,
        summary=_bounded(summary),
        navigation_url=url,
        editable=permission in {"edit", "manage"},
    )


def _describe(object_type: str, row, study: Study) -> tuple[str, str, str | None]:
    if object_type == "analysis_target":
        source = row.activity_response_id or row.evidence_file_id or row.participant_id
        section = "evidence" if row.target_type == "evidence_file" else "entries"
        return (
            "Analysis target",
            f"{row.target_type.replace('_', ' ')} #{source}",
            f"/projects/{study.project_id}/workspace/{section}",
        )
    if object_type == "code_application":
        return (
            "Coded passage",
            f"Code application #{row.id}",
            f"/projects/{study.project_id}/workspace/coding?study_id={study.id}",
        )
    if object_type == "annotation":
        return "Annotation", row.body, f"/projects/{study.project_id}/workspace/entries"
    if object_type == "memo":
        return row.title, row.body, f"/studies/{row.study_id}/memos"
    if object_type == "code":
        return row.name, row.definition, f"/studies/{row.study_id}/codebook"
    if object_type == "theme":
        return row.name, row.description, f"/studies/{row.study_id}/theme-explorer"
    if object_type == "relationship":
        summary = f"{row.source_type} #{row.source_id} {row.relationship_type.replace('_', ' ')} {row.target_type} #{row.target_id}"
        return (
            "Analytical relationship",
            summary,
            f"/studies/{row.study_id}/relationships",
        )
    return (
        f"{row.reference} · {row.name}",
        "Participant / case",
        f"/participants/{row.id}",
    )
