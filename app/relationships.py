from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from .analysis_objects import (
    ANALYTICAL_OBJECT_TYPES,
    analytical_study_permission,
    resolve_analytical_object,
)
from .models import AnalyticalRelationship, Study, User


RELATIONSHIP_TYPES = (
    "supports",
    "contradicts",
    "qualifies",
    "illustrates",
    "derived_from",
    "informed_by",
    "explains",
    "relates_to",
    "precedes",
    "follows",
    "refines",
)
RELATIONSHIP_OBJECT_TYPES = ANALYTICAL_OBJECT_TYPES - {"participant_case", "relationship"}


def parse_object_ref(value: str) -> tuple[str, int]:
    try:
        object_type, raw_id = value.split(":", 1); object_id = int(raw_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Analytical object reference is invalid") from exc
    if object_type not in RELATIONSHIP_OBJECT_TYPES or object_id < 1:
        raise ValueError("Analytical object reference is invalid")
    return object_type, object_id


def create_relationship(db: Session, user: User, *, study_id: int, source_ref: str, relationship_type: str, target_ref: str, rationale: str) -> AnalyticalRelationship:
    source_type, source_id = parse_object_ref(source_ref); target_type, target_id = parse_object_ref(target_ref)
    if relationship_type not in RELATIONSHIP_TYPES: raise ValueError("Relationship type is invalid")
    if (source_type, source_id) == (target_type, target_id): raise ValueError("An object cannot relate to itself")
    for object_type, object_id in ((source_type, source_id), (target_type, target_id)):
        if resolve_analytical_object(
            db,
            user,
            study_id=study_id,
            object_type=object_type,
            object_id=object_id,
            require_edit=True,
        ) is None:
            raise ValueError("Analytical object is unavailable")
    note=rationale.strip()
    if len(note)>2000: raise ValueError("Relationship rationale is too long")
    row=AnalyticalRelationship(organisation_id=user.organisation_id,study_id=study_id,source_type=source_type,source_id=source_id,relationship_type=relationship_type,target_type=target_type,target_id=target_id,rationale=note,created_by_id=user.id)
    db.add(row); return row


def remove_object_relationships(db: Session, object_type: str, object_ids: set[int]) -> None:
    if object_type not in RELATIONSHIP_OBJECT_TYPES or not object_ids: return
    db.execute(delete(AnalyticalRelationship).where(or_(and_(AnalyticalRelationship.source_type==object_type,AnalyticalRelationship.source_id.in_(object_ids)),and_(AnalyticalRelationship.target_type==object_type,AnalyticalRelationship.target_id.in_(object_ids)))))


def changeable_relationship(
    db: Session, user: User, *, study_id: int, relationship_id: int
) -> AnalyticalRelationship:
    study = db.scalar(
        select(Study).where(
            Study.id == study_id,
            Study.organisation_id == user.organisation_id,
        )
    )
    permission = analytical_study_permission(db, user, study) if study else None
    if permission not in {"edit", "manage"}:
        raise PermissionError("Relationship is unavailable")
    row = db.scalar(
        select(AnalyticalRelationship).where(
            AnalyticalRelationship.id == relationship_id,
            AnalyticalRelationship.organisation_id == user.organisation_id,
            AnalyticalRelationship.study_id == study_id,
        )
    )
    if row is None:
        raise ValueError("Relationship is unavailable")
    if row.created_by_id != user.id and permission != "manage":
        raise PermissionError("You cannot remove this relationship")
    return row
