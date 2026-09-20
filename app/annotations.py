from sqlalchemy.orm import Session

from .models import AnalysisTarget, ResearchAnnotation, User
from .passage_coding import text_anchor


MAX_ANNOTATION_LENGTH = 5000


def normalise_annotation_body(body: str) -> str:
    value = body.strip()
    if not value:
        raise ValueError("Annotation text is required")
    if len(value) > MAX_ANNOTATION_LENGTH:
        raise ValueError(f"Annotation text must be {MAX_ANNOTATION_LENGTH} characters or fewer")
    return value


def create_annotation(
    db: Session,
    user: User,
    *,
    target: AnalysisTarget,
    text: str,
    body: str,
    start: int,
    end: int,
) -> ResearchAnnotation:
    if target.organisation_id != user.organisation_id or target.target_type != "activity_response":
        raise PermissionError("Target is unavailable")
    row = ResearchAnnotation(
        organisation_id=user.organisation_id,
        study_id=target.study_id,
        analysis_target_id=target.id,
        author_id=user.id,
        anchor_json=text_anchor(text, start, end),
        body=normalise_annotation_body(body),
    )
    db.add(row)
    return row
