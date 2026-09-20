"""Researcher-scoped canvas layout services.

Canvas rows store only coordinates and typed object pointers. Analytical meaning
continues to live in the underlying object and AnalyticalRelationship records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .analysis_objects import (
    AnalyticalObjectSummary,
    analytical_study_permission,
    list_analytical_objects,
    resolve_analytical_object,
    resolve_analytical_objects,
)
from .models import (
    AnalysisCanvas,
    AnalysisCanvasNode,
    AnalyticalRelationship,
    Study,
    User,
)
from .relationships import parse_object_ref

CANVAS_OBJECT_TYPES = {
    "analysis_target",
    "code_application",
    "annotation",
    "memo",
    "code",
    "theme",
    "finding",
}
MAX_CANVAS_NODES = 100
MAX_CANVAS_RELATIONSHIPS = 500
MAX_COORDINATE = 4000.0


@dataclass(frozen=True)
class CanvasNodeView:
    placement: AnalysisCanvasNode
    object: AnalyticalObjectSummary


def canvas_study_access(db: Session, user: User, study_id: int) -> tuple[Study, str]:
    study = db.scalar(
        select(Study).where(
            Study.id == study_id,
            Study.organisation_id == user.organisation_id,
        )
    )
    permission = analytical_study_permission(db, user, study) if study else None
    if study is None or permission is None:
        raise PermissionError("Analysis canvas is unavailable")
    return study, permission


def user_canvas(db: Session, user: User, study_id: int) -> AnalysisCanvas | None:
    canvas_study_access(db, user, study_id)
    return db.scalar(
        select(AnalysisCanvas).where(
            AnalysisCanvas.organisation_id == user.organisation_id,
            AnalysisCanvas.study_id == study_id,
            AnalysisCanvas.owner_id == user.id,
        )
    )


def _get_or_create_canvas(db: Session, user: User, study_id: int) -> AnalysisCanvas:
    canvas = user_canvas(db, user, study_id)
    if canvas is None:
        canvas = AnalysisCanvas(
            organisation_id=user.organisation_id,
            study_id=study_id,
            owner_id=user.id,
        )
        db.add(canvas)
        db.flush()
    return canvas


def canvas_candidates(
    db: Session, user: User, study_id: int
) -> list[AnalyticalObjectSummary]:
    return list_analytical_objects(
        db,
        user,
        study_id=study_id,
        object_types=CANVAS_OBJECT_TYPES,
        limit_per_type=40,
    )


def canvas_nodes(db: Session, user: User, study_id: int) -> list[CanvasNodeView]:
    canvas = user_canvas(db, user, study_id)
    if canvas is None:
        return []
    placements = db.scalars(
        select(AnalysisCanvasNode)
        .where(
            AnalysisCanvasNode.canvas_id == canvas.id,
            AnalysisCanvasNode.organisation_id == user.organisation_id,
            AnalysisCanvasNode.study_id == study_id,
        )
        .order_by(AnalysisCanvasNode.id)
        .limit(MAX_CANVAS_NODES + 1)
    ).all()
    resolved_objects = resolve_analytical_objects(
        db,
        user,
        study_id=study_id,
        references={
            (placement.object_type, placement.object_id)
            for placement in placements[:MAX_CANVAS_NODES]
        },
    )
    output = []
    for placement in placements[:MAX_CANVAS_NODES]:
        resolved = resolved_objects.get((placement.object_type, placement.object_id))
        if resolved is not None:
            output.append(CanvasNodeView(placement=placement, object=resolved))
    return output


def add_canvas_node(
    db: Session,
    user: User,
    *,
    study_id: int,
    object_ref: str,
) -> AnalysisCanvasNode:
    object_type, object_id = parse_object_ref(object_ref)
    if object_type not in CANVAS_OBJECT_TYPES:
        raise ValueError("This object cannot be placed on the canvas")
    if (
        resolve_analytical_object(
            db,
            user,
            study_id=study_id,
            object_type=object_type,
            object_id=object_id,
        )
        is None
    ):
        raise PermissionError("Analytical object is unavailable")
    canvas = _get_or_create_canvas(db, user, study_id)
    existing = db.scalar(
        select(AnalysisCanvasNode).where(
            AnalysisCanvasNode.canvas_id == canvas.id,
            AnalysisCanvasNode.object_type == object_type,
            AnalysisCanvasNode.object_id == object_id,
        )
    )
    if existing is not None:
        return existing
    count = len(
        db.scalars(
            select(AnalysisCanvasNode.id)
            .where(AnalysisCanvasNode.canvas_id == canvas.id)
            .limit(MAX_CANVAS_NODES + 1)
        ).all()
    )
    if count >= MAX_CANVAS_NODES:
        raise ValueError("A canvas can contain at most 100 objects")
    row = AnalysisCanvasNode(
        organisation_id=user.organisation_id,
        study_id=study_id,
        canvas_id=canvas.id,
        object_type=object_type,
        object_id=object_id,
        x=float(30 + (count % 4) * 270),
        y=float(30 + (count // 4) * 190),
        added_by_id=user.id,
    )
    db.add(row)
    return row


def _owned_node(
    db: Session, user: User, study_id: int, node_id: int
) -> AnalysisCanvasNode:
    canvas_study_access(db, user, study_id)
    row = db.scalar(
        select(AnalysisCanvasNode)
        .join(AnalysisCanvas, AnalysisCanvas.id == AnalysisCanvasNode.canvas_id)
        .where(
            AnalysisCanvasNode.id == node_id,
            AnalysisCanvasNode.organisation_id == user.organisation_id,
            AnalysisCanvasNode.study_id == study_id,
            AnalysisCanvas.owner_id == user.id,
        )
    )
    if row is None:
        raise PermissionError("Canvas object is unavailable")
    return row


def move_canvas_node(
    db: Session,
    user: User,
    *,
    study_id: int,
    node_id: int,
    x: float,
    y: float,
) -> AnalysisCanvasNode:
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("Canvas coordinates are invalid")
    row = _owned_node(db, user, study_id, node_id)
    row.x = min(max(x, 0.0), MAX_COORDINATE)
    row.y = min(max(y, 0.0), MAX_COORDINATE)
    return row


def remove_canvas_node(db: Session, user: User, *, study_id: int, node_id: int) -> None:
    db.delete(_owned_node(db, user, study_id, node_id))


def canvas_relationships(
    db: Session,
    user: User,
    study_id: int,
    nodes: list[CanvasNodeView],
) -> tuple[list[AnalyticalRelationship], bool]:
    canvas_study_access(db, user, study_id)
    refs = {(node.object.object_type, node.object.object_id) for node in nodes}
    if not refs:
        return [], False
    source_filters = [
        (AnalyticalRelationship.source_type == object_type)
        & (AnalyticalRelationship.source_id == object_id)
        for object_type, object_id in refs
    ]
    target_filters = [
        (AnalyticalRelationship.target_type == object_type)
        & (AnalyticalRelationship.target_id == object_id)
        for object_type, object_id in refs
    ]
    rows = db.scalars(
        select(AnalyticalRelationship)
        .where(
            AnalyticalRelationship.organisation_id == user.organisation_id,
            AnalyticalRelationship.study_id == study_id,
            or_(*source_filters),
            or_(*target_filters),
        )
        .order_by(AnalyticalRelationship.created_at, AnalyticalRelationship.id)
        .limit(MAX_CANVAS_RELATIONSHIPS + 1)
    ).all()
    return rows[:MAX_CANVAS_RELATIONSHIPS], len(rows) > MAX_CANVAS_RELATIONSHIPS
