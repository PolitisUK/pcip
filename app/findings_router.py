"""HTTP routes for first-class researcher findings."""

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .analysis_objects import (
    list_analytical_objects,
    resolve_analytical_objects,
)
from .csrf import csrf_protect
from .db import get_db
from .findings import changeable_finding, finding_study_access, finding_text
from .models import AnalyticalRelationship, Project, ResearchAnalysisSuggestion, ResearchFinding, User
from .relationships import (
    RELATIONSHIP_OBJECT_TYPES,
    RELATIONSHIP_TYPES,
    changeable_relationship,
    create_relationship,
)
from .services import audit


def findings_router(
    *, current_user_dependency: Callable, render_page: Callable
) -> APIRouter:
    router = APIRouter(tags=["analysis-workbench"])

    @router.get("/studies/{study_id}/findings", response_class=HTMLResponse)
    def findings_page(
        study_id: int,
        request: Request,
        include_archived: bool = False,
        user=Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ):
        try:
            study, permission = finding_study_access(db, user, study_id)
        except PermissionError as exc:
            raise HTTPException(404, str(exc)) from exc
        statement = select(ResearchFinding).where(
            ResearchFinding.organisation_id == user.organisation_id,
            ResearchFinding.study_id == study.id,
        )
        if not include_archived:
            statement = statement.where(ResearchFinding.archived_at.is_(None))
        findings = db.scalars(
            statement.order_by(ResearchFinding.updated_at.desc()).limit(200)
        ).all()
        suggestion_ids = {row.originating_suggestion_id for row in findings if row.originating_suggestion_id}
        originating_suggestions = {
            row.id: row for row in db.scalars(select(ResearchAnalysisSuggestion).where(
                ResearchAnalysisSuggestion.organisation_id == user.organisation_id,
                ResearchAnalysisSuggestion.study_id == study.id,
                ResearchAnalysisSuggestion.id.in_(suggestion_ids),
            )).all()
        } if suggestion_ids else {}
        finding_ids = {row.id for row in findings}
        relationship_rows = db.scalars(
            select(AnalyticalRelationship)
            .where(
                AnalyticalRelationship.organisation_id == user.organisation_id,
                AnalyticalRelationship.study_id == study.id,
                or_(
                    (AnalyticalRelationship.source_type == "finding")
                    & (AnalyticalRelationship.source_id.in_(finding_ids)),
                    (AnalyticalRelationship.target_type == "finding")
                    & (AnalyticalRelationship.target_id.in_(finding_ids)),
                ),
            )
            .order_by(AnalyticalRelationship.created_at.desc())
            .limit(101)
        ).all() if finding_ids else []
        relationships_truncated = len(relationship_rows) > 100
        relationships = relationship_rows[:100]
        other_refs = {
            (row.target_type, row.target_id)
            if row.source_type == "finding"
            else (row.source_type, row.source_id)
            for row in relationships
        }
        resolved = resolve_analytical_objects(
            db, user, study_id=study.id, references=other_refs
        )
        relationships_by_finding: dict[int, list[dict]] = {}
        for row in relationships:
            finding_id = row.source_id if row.source_type == "finding" else row.target_id
            other_ref = (
                (row.target_type, row.target_id)
                if row.source_type == "finding"
                else (row.source_type, row.source_id)
            )
            relationships_by_finding.setdefault(finding_id, []).append(
                {
                    "relationship": row,
                    "other": resolved.get(other_ref),
                    "direction": "outgoing" if row.source_type == "finding" else "incoming",
                }
            )
        researcher_ids = {row.created_by_id for row in findings} | {
            row.created_by_id for row in relationships
        }
        researchers = {
            row.id: row
            for row in db.scalars(
                select(User).where(
                    User.organisation_id == user.organisation_id,
                    User.id.in_(researcher_ids),
                )
            ).all()
        } if researcher_ids else {}
        can_edit = permission in {"edit", "manage"}
        candidates = (
            list_analytical_objects(
                db,
                user,
                study_id=study.id,
                object_types=set(RELATIONSHIP_OBJECT_TYPES),
                limit_per_type=40,
            )
            if can_edit
            else []
        )
        return render_page(
            request,
            "research_findings.html",
            user=user,
            project=db.get(Project, study.project_id),
            study=study,
            findings=findings,
            originating_suggestions=originating_suggestions,
            relationships_by_finding=relationships_by_finding,
            relationships_truncated=relationships_truncated,
            researchers=researchers,
            candidates=candidates,
            relationship_types=RELATIONSHIP_TYPES,
            can_edit=can_edit,
            can_change={
                row.id: can_edit
                and (permission == "manage" or row.created_by_id == user.id)
                for row in findings
            },
            can_remove_relationship={
                row.id: can_edit
                and (permission == "manage" or row.created_by_id == user.id)
                for row in relationships
            },
            include_archived=include_archived,
        )

    @router.post("/studies/{study_id}/findings")
    def create_finding(
        study_id: int,
        title: str = Form(..., max_length=200),
        body: str = Form(..., max_length=30000),
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            study, permission = finding_study_access(db, user, study_id)
            if permission not in {"edit", "manage"}:
                raise PermissionError("You cannot create findings")
            clean_title, clean_body = finding_text(title, body)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        row = ResearchFinding(
            organisation_id=user.organisation_id,
            study_id=study.id,
            title=clean_title,
            body=clean_body,
            created_by_id=user.id,
        )
        db.add(row)
        db.flush()
        audit(db, user.organisation_id, user.id, "research_finding.created", "research_finding", row.id, "finding created", project_id=study.project_id, study_id=study.id)
        db.commit()
        return RedirectResponse(f"/studies/{study.id}/findings#finding-{row.id}", 303)

    @router.post("/studies/{study_id}/findings/{finding_id}/edit")
    def edit_finding(
        study_id: int,
        finding_id: int,
        title: str = Form(..., max_length=200),
        body: str = Form(..., max_length=30000),
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            study, permission = finding_study_access(db, user, study_id)
            if permission not in {"edit", "manage"}:
                raise PermissionError("You cannot link findings")
            row = db.scalar(
                select(ResearchFinding).where(
                    ResearchFinding.id == finding_id,
                    ResearchFinding.organisation_id == user.organisation_id,
                    ResearchFinding.study_id == study_id,
                )
            )
            if row is None:
                raise ValueError("Finding is unavailable")
            if row.archived_at is not None:
                raise ValueError("Restore this finding before editing it")
            row.title, row.body = finding_text(title, body)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409 if "Restore" in str(exc) else 400, str(exc)) from exc
        audit(db, user.organisation_id, user.id, "research_finding.updated", "research_finding", row.id, "finding content updated", project_id=study.project_id, study_id=study.id)
        db.commit()
        return RedirectResponse(f"/studies/{study_id}/findings#finding-{row.id}", 303)

    @router.post("/studies/{study_id}/findings/{finding_id}/lifecycle/{action}")
    def finding_archive(
        study_id: int,
        finding_id: int,
        action: str,
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        if action not in {"archive", "restore"}:
            raise HTTPException(404, "Finding action not found")
        try:
            study, _ = finding_study_access(db, user, study_id)
            row = changeable_finding(db, user, study_id=study_id, finding_id=finding_id)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        row.archived_at = datetime.now(timezone.utc) if action == "archive" else None
        row.archived_by_id = user.id if action == "archive" else None
        audit(db, user.organisation_id, user.id, f"research_finding.{action}d", "research_finding", row.id, f"finding {action}d", project_id=study.project_id, study_id=study.id)
        db.commit()
        return RedirectResponse(f"/studies/{study_id}/findings?include_archived=true#finding-{row.id}", 303)

    @router.post("/studies/{study_id}/findings/{finding_id}/relationships")
    def link_finding(
        study_id: int,
        finding_id: int,
        relationship_type: str = Form(..., max_length=30),
        target_ref: str = Form(..., max_length=80),
        direction: str = Form(
            "evidence_to_finding", pattern="^(evidence_to_finding|finding_to_evidence)$"
        ),
        rationale: str = Form("", max_length=2000),
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            study, _ = finding_study_access(db, user, study_id)
            row = changeable_finding(db, user, study_id=study_id, finding_id=finding_id)
            if row.archived_at is not None:
                raise ValueError("Restore this finding before linking evidence")
            relationship = create_relationship(
                db,
                user,
                study_id=study_id,
                source_ref=(
                    target_ref
                    if direction == "evidence_to_finding"
                    else f"finding:{row.id}"
                ),
                relationship_type=relationship_type,
                target_ref=(
                    f"finding:{row.id}"
                    if direction == "evidence_to_finding"
                    else target_ref
                ),
                rationale=rationale,
            )
            db.flush()
        except PermissionError as exc:
            db.rollback()
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "That finding link already exists") from exc
        audit(db, user.organisation_id, user.id, "analytical_relationship.created", "analytical_relationship", relationship.id, relationship.relationship_type, project_id=study.project_id, study_id=study.id)
        db.commit()
        return RedirectResponse(f"/studies/{study_id}/findings#finding-{row.id}", 303)

    @router.post("/studies/{study_id}/findings/{finding_id}/relationships/{relationship_id}/delete")
    def unlink_finding(
        study_id: int,
        finding_id: int,
        relationship_id: int,
        user=Depends(current_user_dependency),
        csrf_ok: None = Depends(csrf_protect),
        db: Session = Depends(get_db),
    ):
        try:
            study, permission = finding_study_access(db, user, study_id)
            if permission not in {"edit", "manage"}:
                raise PermissionError("You cannot unlink findings")
            finding = db.scalar(
                select(ResearchFinding).where(
                    ResearchFinding.id == finding_id,
                    ResearchFinding.organisation_id == user.organisation_id,
                    ResearchFinding.study_id == study_id,
                )
            )
            if finding is None:
                raise ValueError("Finding is unavailable")
            relationship = changeable_relationship(
                db, user, study_id=study_id, relationship_id=relationship_id
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        if not (
            (relationship.source_type == "finding" and relationship.source_id == finding.id)
            or (relationship.target_type == "finding" and relationship.target_id == finding.id)
        ):
            raise HTTPException(404, "Finding link is unavailable")
        audit(db, user.organisation_id, user.id, "analytical_relationship.removed", "analytical_relationship", relationship.id, relationship.relationship_type, project_id=study.project_id, study_id=study.id)
        db.delete(relationship)
        db.commit()
        return RedirectResponse(f"/studies/{study_id}/findings#finding-{finding.id}", 303)

    return router
