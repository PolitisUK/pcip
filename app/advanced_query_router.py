"""Routes for bounded advanced Analysis Workbench queries."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .advanced_queries import AdvancedQueryFilters, advanced_query
from .db import get_db
from .models import (
    ActivityResponse,
    CodeApplication,
    Participant,
    ResearchCode,
    ResearchTheme,
    User,
)
from .relationships import RELATIONSHIP_TYPES


def _date(value: str, *, upper: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(422, "Query dates must use YYYY-MM-DD.") from exc
    return parsed + timedelta(days=1) if upper else parsed


def advanced_query_router(
    *,
    current_user_dependency: Callable,
    render_page: Callable,
    workspace_scope: Callable,
) -> APIRouter:
    router = APIRouter(tags=["analysis-workbench"])

    @router.get(
        "/projects/{project_id}/workspace/queries", response_class=HTMLResponse
    )
    def query_page(
        project_id: int,
        request: Request,
        study_id: int | None = Query(None, ge=1),
        include_code_id: list[int] = Query(default=[]),
        exclude_code_id: list[int] = Query(default=[]),
        operator: str = Query("and", pattern="^(and|or)$"),
        theme_id: int | None = Query(None, ge=1),
        researcher_id: int | None = Query(None, ge=1),
        participant_id: int | None = Query(None, ge=1),
        date_from: str = Query("", max_length=10),
        date_to: str = Query("", max_length=10),
        relationship_type: str = Query("", max_length=30),
        page: int = Query(1, ge=1),
        user=Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ):
        project, studies = workspace_scope(db, user, project_id)
        accessible_study_ids = {row.id for row in studies}
        if study_id is not None and study_id not in accessible_study_ids:
            raise HTTPException(404, "Study not found")
        study_ids = (study_id,) if study_id else tuple(sorted(accessible_study_ids))
        codes = db.scalars(
            select(ResearchCode)
            .where(
                ResearchCode.organisation_id == user.organisation_id,
                ResearchCode.study_id.in_(study_ids),
            )
            .order_by(ResearchCode.name)
            .limit(1000)
        ).all() if study_ids else []
        themes = db.scalars(
            select(ResearchTheme)
            .where(
                ResearchTheme.organisation_id == user.organisation_id,
                ResearchTheme.study_id.in_(study_ids),
            )
            .order_by(ResearchTheme.name)
            .limit(500)
        ).all() if study_ids else []
        participants = db.scalars(
            select(Participant)
            .join(ActivityResponse, ActivityResponse.participant_id == Participant.id)
            .where(
                Participant.organisation_id == user.organisation_id,
                ActivityResponse.organisation_id == user.organisation_id,
                ActivityResponse.study_id.in_(study_ids),
            )
            .distinct()
            .order_by(Participant.reference)
            .limit(1000)
        ).all() if study_ids else []
        researchers = db.scalars(
            select(User)
            .join(CodeApplication, CodeApplication.applied_by_id == User.id)
            .where(
                User.organisation_id == user.organisation_id,
                CodeApplication.organisation_id == user.organisation_id,
                CodeApplication.study_id.in_(study_ids),
            )
            .distinct()
            .order_by(User.name)
            .limit(500)
        ).all() if study_ids else []

        code_ids = {row.id for row in codes}
        selected_include = frozenset(include_code_id)
        selected_exclude = frozenset(exclude_code_id)
        if not (selected_include | selected_exclude) <= code_ids:
            raise HTTPException(404, "Research code not found")
        if theme_id is not None and theme_id not in {row.id for row in themes}:
            raise HTTPException(404, "Theme not found")
        if participant_id is not None and participant_id not in {row.id for row in participants}:
            raise HTTPException(404, "Participant not found")
        if researcher_id is not None and researcher_id not in {row.id for row in researchers}:
            raise HTTPException(404, "Researcher not found")
        selected_relationship = relationship_type or None
        if selected_relationship is not None and selected_relationship not in RELATIONSHIP_TYPES:
            raise HTTPException(422, "Relationship type is invalid")

        query = advanced_query(
            db,
            user,
            AdvancedQueryFilters(
                study_ids=study_ids,
                include_code_ids=selected_include,
                exclude_code_ids=selected_exclude,
                operator=operator,
                theme_id=theme_id,
                researcher_id=researcher_id,
                participant_id=participant_id,
                date_from=_date(date_from),
                date_to=_date(date_to, upper=True),
                relationship_type=selected_relationship,
            ),
            page=page,
        )
        params = request.query_params.multi_items()

        def page_url(target: int) -> str:
            kept = [(key, value) for key, value in params if key != "page"]
            kept.append(("page", str(target)))
            return f"{request.url.path}?{urlencode(kept)}"

        code_map = {row.id: row for row in codes}
        return render_page(
            request,
            "advanced_queries.html",
            user=user,
            project=project,
            workspace_studies=studies,
            query=query,
            codes=codes,
            code_map=code_map,
            themes=themes,
            participants=participants,
            researchers=researchers,
            relationship_types=RELATIONSHIP_TYPES,
            filters={
                "study_id": study_id,
                "include_code_ids": selected_include,
                "exclude_code_ids": selected_exclude,
                "operator": operator,
                "theme_id": theme_id,
                "researcher_id": researcher_id,
                "participant_id": participant_id,
                "date_from": date_from,
                "date_to": date_to,
                "relationship_type": selected_relationship,
            },
            previous_url=page_url(query.page - 1) if query.page > 1 else None,
            next_url=page_url(query.page + 1) if query.page < query.pages else None,
        )

    return router
