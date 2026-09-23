"""Read-only projection of canonical audit events for an analysis workspace."""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    AnalysisTarget,
    AnalyticalRelationship,
    AuditEvent,
    CodeApplication,
    ResearchAnalysisSuggestion,
    ResearchAnnotation,
    ResearchCode,
    ResearchFinding,
    ResearchMemo,
    ResearchTheme,
    ResearchThemeCode,
    Study,
    User,
)

ACTION_FAMILIES = {
    "research_code": "Code lifecycle",
    "code_application": "Passage coding",
    "research_annotation": "Annotations",
    "research_memo": "Memos",
    "analytical_relationship": "Relationships",
    "research_theme": "Theme development",
    "research_finding": "Finding development",
    "research_analysis": "AI suggestion review",
    "research_assistant": "AI assistant queries",
    "evidence_region": "Image-region analysis",
    "analysis_export": "Analysis exports",
}

ENTITY_MODELS = {
    "analysis_target": AnalysisTarget,
    "code_application": CodeApplication,
    "research_annotation": ResearchAnnotation,
    "research_memo": ResearchMemo,
    "analytical_relationship": AnalyticalRelationship,
    "research_code": ResearchCode,
    "research_theme": ResearchTheme,
    "research_theme_code": ResearchThemeCode,
    "research_finding": ResearchFinding,
    "research_analysis_suggestion": ResearchAnalysisSuggestion,
}


def _legacy_context(db: Session, events: list[AuditEvent]) -> dict[tuple[str, int], tuple[int, int]]:
    """Resolve context for historical events while the canonical object exists."""
    identifiers: dict[str, set[int]] = {}
    for event in events:
        if event.study_id is not None or event.entity_type not in ENTITY_MODELS:
            continue
        try:
            identifier = int(event.entity_id)
        except (TypeError, ValueError):
            continue
        identifiers.setdefault(event.entity_type, set()).add(identifier)
    resolved: dict[tuple[str, int], tuple[int, int]] = {}
    for entity_type, entity_ids in identifiers.items():
        model = ENTITY_MODELS[entity_type]
        for row in db.scalars(select(model).where(model.id.in_(entity_ids))).all():
            resolved[(entity_type, row.id)] = (row.organisation_id, row.study_id)
    return resolved


def analysis_audit_page(
    db: Session,
    user: User,
    project_id: int,
    studies: list[Study],
    *,
    page: int,
    study_id: int | None = None,
    actor_user_id: int | None = None,
    action_family: str = "",
    entity_type: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    per_page: int = 50,
) -> tuple[list[dict], int, int, bool, dict[int, User]]:
    visible_studies = {row.id: row for row in studies}
    if study_id is not None and study_id not in visible_studies:
        raise ValueError("Study is unavailable in this workspace")
    if action_family and action_family not in ACTION_FAMILIES:
        raise ValueError("Unknown analysis action filter")
    if entity_type and entity_type not in ENTITY_MODELS:
        raise ValueError("Unknown analysis object filter")

    statement = select(AuditEvent).where(
        AuditEvent.organisation_id == user.organisation_id,
        or_(*(AuditEvent.action.like(f"{prefix}.%") for prefix in ACTION_FAMILIES)),
    )
    if actor_user_id is not None:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if action_family:
        statement = statement.where(AuditEvent.action.like(f"{action_family}.%"))
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if date_from is not None:
        statement = statement.where(AuditEvent.created_at >= date_from)
    if date_to is not None:
        statement = statement.where(AuditEvent.created_at < date_to)
    candidates = db.scalars(statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(5001)).all()
    truncated = len(candidates) > 5000
    candidates = candidates[:5000]
    legacy = _legacy_context(db, candidates)

    scoped: list[tuple[AuditEvent, Study]] = []
    for event in candidates:
        event_study_id = event.study_id
        event_project_id = event.project_id
        if event_study_id is None:
            try:
                key = (event.entity_type, int(event.entity_id))
            except (TypeError, ValueError):
                continue
            resolved = legacy.get(key)
            if resolved is None or resolved[0] != user.organisation_id:
                continue
            event_study_id = resolved[1]
        study = visible_studies.get(event_study_id)
        if study is None or study.project_id != project_id:
            continue
        if event_project_id is not None and event_project_id != project_id:
            continue
        if study_id is not None and event_study_id != study_id:
            continue
        scoped.append((event, study))

    total = len(scoped)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    selected = scoped[(page - 1) * per_page : page * per_page]
    actor_ids = {event.actor_user_id for event, _ in scoped if event.actor_user_id is not None}
    actors = {
        row.id: row
        for row in db.scalars(select(User).where(
            User.organisation_id == user.organisation_id,
            User.id.in_(actor_ids),
        )).all()
    } if actor_ids else {}
    rows = [{"event": event, "study": study, "actor": actors.get(event.actor_user_id)} for event, study in selected]
    return rows, total, pages, truncated, actors
