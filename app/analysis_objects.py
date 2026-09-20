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
    ActivityResponse,
    AnalysisTarget,
    AnalyticalRelationship,
    CodeApplication,
    EvidenceFile,
    Participant,
    ResearchAnnotation,
    ResearchCode,
    ResearchFinding,
    ResearchMemo,
    ResearchTheme,
    Study,
    StudyAccess,
    StudyEnrolment,
    User,
)
from .passage_coding import verified_passage
from .research_workspace import response_body

ANALYTICAL_OBJECT_TYPES = frozenset(
    {
        "analysis_target",
        "code_application",
        "annotation",
        "memo",
        "code",
        "theme",
        "finding",
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
        "finding": ResearchFinding,
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
    if require_edit and object_type == "finding" and row.archived_at is not None:
        return None
    label, summary, url = _describe(db, object_type, row, study)
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


def list_analytical_objects(
    db: Session,
    user: User,
    *,
    study_id: int,
    object_types: set[str],
    limit_per_type: int = 40,
) -> list[AnalyticalObjectSummary]:
    """List a bounded, explicit set of object types for pickers and canvases."""
    allowed = object_types & ANALYTICAL_OBJECT_TYPES - {
        "relationship",
        "participant_case",
    }
    if not allowed:
        return []
    study = db.scalar(
        select(Study).where(
            Study.id == study_id, Study.organisation_id == user.organisation_id
        )
    )
    permission = analytical_study_permission(db, user, study) if study else None
    if permission is None:
        return []
    safe_limit = min(max(limit_per_type, 1), 50)
    models = {
        "analysis_target": AnalysisTarget,
        "code_application": CodeApplication,
        "annotation": ResearchAnnotation,
        "memo": ResearchMemo,
        "code": ResearchCode,
        "theme": ResearchTheme,
        "finding": ResearchFinding,
    }
    output = []
    for object_type in sorted(allowed):
        model = models[object_type]
        rows = db.scalars(
            select(model)
            .where(
                model.organisation_id == user.organisation_id,
                model.study_id == study_id,
            )
            .order_by(model.id.desc())
            .limit(safe_limit)
        ).all()
        coded_details = (
            _coded_application_details(db, rows)
            if object_type == "code_application"
            else {}
        )
        for row in rows:
            label, summary, url = _describe(
                db,
                object_type,
                row,
                study,
                coded_detail=coded_details.get(row.id),
            )
            output.append(
                AnalyticalObjectSummary(
                    object_type=object_type,
                    object_id=row.id,
                    organisation_id=user.organisation_id,
                    study_id=study_id,
                    label=label,
                    summary=_bounded(summary),
                    navigation_url=url,
                    editable=permission in {"edit", "manage"},
                )
            )
    return output


def resolve_analytical_objects(
    db: Session,
    user: User,
    *,
    study_id: int,
    references: set[tuple[str, int]],
) -> dict[tuple[str, int], AnalyticalObjectSummary]:
    """Bulk-resolve a bounded set of typed references without per-node scope queries."""
    references = {
        (object_type, object_id)
        for object_type, object_id in references
        if object_type in ANALYTICAL_OBJECT_TYPES
        and object_type not in {"relationship", "participant_case"}
        and object_id > 0
    }
    if not references or len(references) > 100:
        return {}
    study = db.scalar(
        select(Study).where(
            Study.id == study_id,
            Study.organisation_id == user.organisation_id,
        )
    )
    permission = analytical_study_permission(db, user, study) if study else None
    if permission is None:
        return {}
    models = {
        "analysis_target": AnalysisTarget,
        "code_application": CodeApplication,
        "annotation": ResearchAnnotation,
        "memo": ResearchMemo,
        "code": ResearchCode,
        "theme": ResearchTheme,
        "finding": ResearchFinding,
    }
    output = {}
    for object_type, model in models.items():
        identifiers = {
            object_id
            for candidate_type, object_id in references
            if candidate_type == object_type
        }
        if not identifiers:
            continue
        rows = db.scalars(
            select(model).where(
                model.id.in_(identifiers),
                model.organisation_id == user.organisation_id,
                model.study_id == study_id,
            )
        ).all()
        coded_details = (
            _coded_application_details(db, rows)
            if object_type == "code_application"
            else {}
        )
        for row in rows:
            label, summary, url = _describe(
                db,
                object_type,
                row,
                study,
                coded_detail=coded_details.get(row.id),
            )
            output[(object_type, row.id)] = AnalyticalObjectSummary(
                object_type=object_type,
                object_id=row.id,
                organisation_id=user.organisation_id,
                study_id=study_id,
                label=label,
                summary=_bounded(summary),
                navigation_url=url,
                editable=permission in {"edit", "manage"},
            )
    return output


def _coded_application_details(
    db: Session, rows: list[CodeApplication]
) -> dict[int, tuple[ResearchCode, ActivityResponse]]:
    identifiers = [row.id for row in rows]
    if not identifiers:
        return {}
    details = db.execute(
        select(CodeApplication.id, ResearchCode, ActivityResponse)
        .select_from(CodeApplication)
        .join(AnalysisTarget, AnalysisTarget.id == CodeApplication.analysis_target_id)
        .join(
            ActivityResponse, ActivityResponse.id == AnalysisTarget.activity_response_id
        )
        .join(ResearchCode, ResearchCode.id == CodeApplication.research_code_id)
        .where(
            CodeApplication.id.in_(identifiers),
            ResearchCode.organisation_id == CodeApplication.organisation_id,
            ResearchCode.study_id == CodeApplication.study_id,
            AnalysisTarget.organisation_id == CodeApplication.organisation_id,
            AnalysisTarget.study_id == CodeApplication.study_id,
            ActivityResponse.organisation_id == CodeApplication.organisation_id,
            ActivityResponse.study_id == CodeApplication.study_id,
        )
    ).all()
    return {
        application_id: (code, response) for application_id, code, response in details
    }


def _describe(
    db: Session,
    object_type: str,
    row,
    study: Study,
    *,
    coded_detail: tuple[ResearchCode, ActivityResponse] | None = None,
) -> tuple[str, str, str | None]:
    def response_url(response: ActivityResponse) -> str:
        return (
            f"/projects/{study.project_id}/workspace/entries"
            f"?participant_id={response.participant_id}"
            f"&prompt_id={response.activity_id}#response-{response.id}"
        )

    if object_type == "analysis_target":
        if row.target_type == "participant_case":
            participant = db.scalar(
                select(Participant).where(
                    Participant.id == row.participant_id,
                    Participant.organisation_id == row.organisation_id,
                )
            )
            if participant:
                return (
                    f"Participant / case · {participant.reference}",
                    participant.name,
                    f"/participants/{participant.id}",
                )
        if row.target_type == "evidence_file":
            evidence = db.scalar(
                select(EvidenceFile).where(
                    EvidenceFile.id == row.evidence_file_id,
                    EvidenceFile.organisation_id == row.organisation_id,
                    EvidenceFile.study_id == row.study_id,
                )
            )
            if evidence:
                return (
                    f"Evidence region · {evidence.original_name}",
                    "Image or file evidence analysis target",
                    f"/evidence/{evidence.id}/analysis",
                )
        if row.target_type == "activity_response":
            response = db.scalar(
                select(ActivityResponse).where(
                    ActivityResponse.id == row.activity_response_id,
                    ActivityResponse.organisation_id == row.organisation_id,
                    ActivityResponse.study_id == row.study_id,
                )
            )
            if response:
                return (
                    f"Source entry #{response.id}",
                    response_body(response.value_json),
                    response_url(response),
                )
        source = row.activity_response_id or row.evidence_file_id or row.participant_id
        return (
            "Analysis target",
            f"{row.target_type.replace('_', ' ')} #{source}",
            f"/projects/{study.project_id}/workspace/entries",
        )
    if object_type == "code_application":
        detail = coded_detail or _coded_application_details(db, [row]).get(row.id)
        if detail:
            code, response = detail
            passage = verified_passage(
                response_body(response.value_json), row.anchor_json
            )
            summary = (
                passage
                if passage is not None
                else "Source passage could not be verified"
            )
            return (
                f"Coded passage · {code.name}",
                summary,
                response_url(response),
            )
        target = db.scalar(select(AnalysisTarget).where(
            AnalysisTarget.id == row.analysis_target_id,
            AnalysisTarget.organisation_id == row.organisation_id,
            AnalysisTarget.study_id == row.study_id,
        ))
        code = db.scalar(select(ResearchCode).where(
            ResearchCode.id == row.research_code_id,
            ResearchCode.organisation_id == row.organisation_id,
            ResearchCode.study_id == row.study_id,
        ))
        if target is not None and target.target_type == "evidence_file":
            _, summary, url = _describe(db, "analysis_target", target, study)
            return f"Coded image region · {code.name if code else 'Unavailable code'}", summary, url
        return (
            "Coded passage",
            f"Code application #{row.id}",
            f"/projects/{study.project_id}/workspace/coding?study_id={study.id}",
        )
    if object_type == "annotation":
        target = db.scalar(select(AnalysisTarget).where(
            AnalysisTarget.id == row.analysis_target_id,
            AnalysisTarget.organisation_id == row.organisation_id,
            AnalysisTarget.study_id == row.study_id,
        ))
        if target is not None:
            _, _, url = _describe(db, "analysis_target", target, study)
        else:
            url = f"/projects/{study.project_id}/workspace/entries"
        return "Annotation", row.body, url
    if object_type == "memo":
        return row.title, row.body, f"/studies/{row.study_id}/memos"
    if object_type == "code":
        return row.name, row.definition, f"/studies/{row.study_id}/codebook"
    if object_type == "theme":
        return row.name, row.description, f"/studies/{row.study_id}/theme-explorer"
    if object_type == "finding":
        return row.title, row.body, f"/studies/{row.study_id}/findings#finding-{row.id}"
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
