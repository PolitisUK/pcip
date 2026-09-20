"""FastAPI routes for the visual Analysis Workbench canvas."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .analysis_canvas import (
    add_canvas_node,
    canvas_candidates,
    canvas_nodes,
    canvas_relationships,
    canvas_study_access,
    move_canvas_node,
    remove_canvas_node,
    user_canvas,
)
from .csrf import csrf_protect
from .db import get_db
from .models import Project, User
from .relationships import (
    RELATIONSHIP_TYPES,
    changeable_relationship,
    create_relationship,
)
from .services import audit


def analysis_canvas_router(
    *, current_user_dependency: Callable, render_page: Callable
) -> APIRouter:
    router = APIRouter(tags=["analysis-workbench"])

    @router.get("/studies/{study_id}/canvas", response_class=HTMLResponse)
    def canvas_page(
        study_id: int,
        request: Request,
        user=Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ):
        try:
            study, permission = canvas_study_access(db, user, study_id)
        except PermissionError as exc:
            raise HTTPException(404, str(exc)) from exc
        nodes = canvas_nodes(db, user, study.id)
        relationships, relationships_truncated = canvas_relationships(
            db, user, study.id, nodes
        )
        placed_refs = {
            (item.object.object_type, item.object.object_id) for item in nodes
        }
        candidates = [
            item
            for item in canvas_candidates(db, user, study.id)
            if (item.object_type, item.object_id) not in placed_refs
        ]
        researcher_ids = {row.created_by_id for row in relationships}
        researchers = (
            {
                row.id: row
                for row in db.scalars(
                    select(User).where(
                        User.organisation_id == user.organisation_id,
                        User.id.in_(researcher_ids),
                    )
                ).all()
            }
            if researcher_ids
            else {}
        )
        return render_page(
            request,
            "analysis_canvas.html",
            user=user,
            study=study,
            project=db.get(Project, study.project_id),
            canvas=user_canvas(db, user, study.id),
            nodes=nodes,
            node_labels={
                f"{item.object.object_type}:{item.object.object_id}": item.object.label
                for item in nodes
            },
            candidates=candidates,
            relationships=relationships,
            relationships_truncated=relationships_truncated,
            researchers=researchers,
            relationship_types=RELATIONSHIP_TYPES,
            can_edit_relationships=permission in {"edit", "manage"},
            can_remove_relationship={
                row.id: permission == "manage" or row.created_by_id == user.id
                for row in relationships
            },
        )

    @router.post("/studies/{study_id}/canvas/nodes")
    def add_node(
        study_id: int,
        object_ref: str = Form(..., max_length=80),
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            add_canvas_node(db, user, study_id=study_id, object_ref=object_ref)
            db.commit()
        except PermissionError as exc:
            db.rollback()
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "That object is already on the canvas") from exc
        return RedirectResponse(f"/studies/{study_id}/canvas", 303)

    @router.post("/studies/{study_id}/canvas/nodes/{node_id}/move")
    def move_node(
        study_id: int,
        node_id: int,
        x: float = Form(...),
        y: float = Form(...),
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            move_canvas_node(db, user, study_id=study_id, node_id=node_id, x=x, y=y)
            db.commit()
        except PermissionError as exc:
            db.rollback()
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(f"/studies/{study_id}/canvas", 303)

    @router.post("/studies/{study_id}/canvas/nodes/{node_id}/delete")
    def remove_node(
        study_id: int,
        node_id: int,
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            remove_canvas_node(db, user, study_id=study_id, node_id=node_id)
            db.commit()
        except PermissionError as exc:
            db.rollback()
            raise HTTPException(404, str(exc)) from exc
        return RedirectResponse(f"/studies/{study_id}/canvas", 303)

    @router.post("/studies/{study_id}/canvas/relationships")
    def add_relationship(
        study_id: int,
        source_ref: str = Form(..., max_length=80),
        relationship_type: str = Form(..., max_length=30),
        target_ref: str = Form(..., max_length=80),
        rationale: str = Form("", max_length=2000),
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            _, permission = canvas_study_access(db, user, study_id)
            if permission not in {"edit", "manage"}:
                raise PermissionError("You cannot create analytical relationships")
            row = create_relationship(
                db,
                user,
                study_id=study_id,
                source_ref=source_ref,
                relationship_type=relationship_type,
                target_ref=target_ref,
                rationale=rationale,
            )
            db.flush()
            audit(
                db,
                user.organisation_id,
                user.id,
                "analytical_relationship.created",
                "analytical_relationship",
                row.id,
                row.relationship_type,
            )
            db.commit()
        except PermissionError as exc:
            db.rollback()
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "That relationship already exists") from exc
        return RedirectResponse(f"/studies/{study_id}/canvas", 303)

    @router.post("/studies/{study_id}/canvas/relationships/{relationship_id}/delete")
    def remove_relationship(
        study_id: int,
        relationship_id: int,
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            row = changeable_relationship(
                db,
                user,
                study_id=study_id,
                relationship_id=relationship_id,
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        audit(
            db,
            user.organisation_id,
            user.id,
            "analytical_relationship.removed",
            "analytical_relationship",
            row.id,
            row.relationship_type,
        )
        db.delete(row)
        db.commit()
        return RedirectResponse(f"/studies/{study_id}/canvas", 303)

    return router
