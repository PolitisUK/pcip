import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AnalysisTarget, CodeApplication, ResearchCode, User


def text_anchor(text: str, start: int, end: int) -> str:
    if start < 0 or start >= end or end > len(text): raise ValueError("Invalid passage offsets")
    selected = text[start:end]
    return json.dumps({"version": 1, "start": start, "end": end, "fingerprint": hashlib.sha256(selected.encode()).hexdigest()}, separators=(",", ":"))


def apply_codes(db: Session, user: User, *, target: AnalysisTarget, text: str, code_ids: list[int], start: int, end: int):
    if target.organisation_id != user.organisation_id or target.target_type != "activity_response": raise PermissionError("Target is unavailable")
    anchor = text_anchor(text, start, end)
    codes = db.scalars(select(ResearchCode).where(ResearchCode.id.in_(code_ids))).all()
    if len(codes) != len(set(code_ids)) or any(c.organisation_id != user.organisation_id or c.study_id != target.study_id or c.archived_at is not None for c in codes): raise ValueError("One or more active codes are unavailable")
    rows = [CodeApplication(organisation_id=user.organisation_id, study_id=target.study_id, analysis_target_id=target.id, research_code_id=c.id, applied_by_id=user.id, anchor_json=anchor) for c in codes]
    db.add_all(rows); return rows
