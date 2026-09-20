import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .annotations import normalise_annotation_body
from .models import AnalysisTarget, CodeApplication, ResearchAnnotation, ResearchCode, User


def region_anchor(x: float, y: float, width: float, height: float) -> str:
    values = (x, y, width, height)
    if any(not isinstance(value, (int, float)) for value in values):
        raise ValueError("Region coordinates are invalid")
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise ValueError("Region must fit within the image")
    return json.dumps({"version": 1, "type": "image_rectangle", "unit": "fraction", "x": round(x, 6), "y": round(y, 6), "width": round(width, 6), "height": round(height, 6)}, separators=(",", ":"))


def parsed_region(anchor_json: str) -> dict | None:
    try:
        anchor = json.loads(anchor_json)
        if not isinstance(anchor, dict) or anchor.get("version") != 1 or anchor.get("type") != "image_rectangle" or anchor.get("unit") != "fraction": return None
        region_anchor(anchor["x"], anchor["y"], anchor["width"], anchor["height"])
        return anchor
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def create_image_region(db: Session, user: User, *, study_id: int, evidence_id: int, x: float, y: float, width: float, height: float, code_ids: list[int], annotation_body: str) -> tuple[AnalysisTarget, list[CodeApplication], ResearchAnnotation | None]:
    anchor = region_anchor(x, y, width, height)
    unique_code_ids = set(code_ids)
    codes = db.scalars(select(ResearchCode).where(ResearchCode.id.in_(unique_code_ids))).all() if unique_code_ids else []
    if len(codes) != len(unique_code_ids) or any(code.organisation_id != user.organisation_id or code.study_id != study_id or code.archived_at is not None for code in codes):
        raise ValueError("One or more active codes are unavailable")
    annotation_text = normalise_annotation_body(annotation_body) if annotation_body.strip() else ""
    if not codes and not annotation_text:
        raise ValueError("Choose a code or add an annotation")
    target = AnalysisTarget(organisation_id=user.organisation_id, study_id=study_id, target_type="evidence_file", evidence_file_id=evidence_id, anchor_json=anchor, authorship="researcher", created_by_id=user.id)
    db.add(target); db.flush()
    applications = [CodeApplication(organisation_id=user.organisation_id, study_id=study_id, analysis_target_id=target.id, research_code_id=code.id, applied_by_id=user.id, anchor_json=anchor) for code in codes]
    annotation = ResearchAnnotation(organisation_id=user.organisation_id, study_id=study_id, analysis_target_id=target.id, author_id=user.id, anchor_json=anchor, body=annotation_text) if annotation_text else None
    db.add_all(applications + ([annotation] if annotation else []))
    return target, applications, annotation
