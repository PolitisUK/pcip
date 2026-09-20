from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ActivityResponse,
    AnalysisTarget,
    Participant,
    ResearchCode,
    ResearchMemo,
    ResearchTheme,
    StudyEnrolment,
    User,
)


SCOPE_FIELDS = {
    "participant": "participant_id",
    "response": "activity_response_id",
    "analysis_target": "analysis_target_id",
    "code": "research_code_id",
    "theme": "research_theme_id",
}


def memo_text(title: str, body: str) -> tuple[str, str]:
    clean_title, clean_body = title.strip(), body.strip()
    if not clean_title or not clean_body:
        raise ValueError("Memo title and text are required")
    if len(clean_title) > 200 or len(clean_body) > 20000:
        raise ValueError("Memo content is too long")
    return clean_title, clean_body


def memo_scope(db: Session, *, organisation_id: int, study_id: int, scope_ref: str) -> dict:
    if scope_ref == "study":
        return {"scope_type": "study"}
    try:
        scope_type, raw_id = scope_ref.split(":", 1)
        object_id = int(raw_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Memo scope is invalid") from exc
    if object_id < 1 or scope_type not in SCOPE_FIELDS:
        raise ValueError("Memo scope is invalid")
    if scope_type == "participant":
        found = db.scalar(select(Participant.id).join(StudyEnrolment, StudyEnrolment.participant_id == Participant.id).where(Participant.id == object_id, Participant.organisation_id == organisation_id, StudyEnrolment.organisation_id == organisation_id, StudyEnrolment.study_id == study_id))
    else:
        model = {"response": ActivityResponse, "analysis_target": AnalysisTarget, "code": ResearchCode, "theme": ResearchTheme}[scope_type]
        found = db.scalar(select(model.id).where(model.id == object_id, model.organisation_id == organisation_id, model.study_id == study_id))
    if found is None:
        raise ValueError("Memo scope is unavailable")
    return {"scope_type": scope_type, SCOPE_FIELDS[scope_type]: object_id}


def create_memo(db: Session, user: User, *, study_id: int, scope_ref: str, title: str, body: str) -> ResearchMemo:
    clean_title, clean_body = memo_text(title, body)
    row = ResearchMemo(organisation_id=user.organisation_id, study_id=study_id, author_id=user.id, title=clean_title, body=clean_body, **memo_scope(db, organisation_id=user.organisation_id, study_id=study_id, scope_ref=scope_ref))
    db.add(row)
    return row
