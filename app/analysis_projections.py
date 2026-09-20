"""Bounded source-traceable projections shared by Analysis Workbench views."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Activity,
    ActivityResponse,
    AnalysisTarget,
    CodeApplication,
    Participant,
    ResearchCode,
    User,
)
from .passage_coding import verified_passage
from .research_workspace import response_body, response_context


@dataclass(frozen=True)
class CodedPassageProjection:
    application: CodeApplication
    target: AnalysisTarget
    response: ActivityResponse
    participant: Participant
    code: ResearchCode
    researcher: User
    activity: Activity
    passage: str | None
    response_text: str
    context: dict[str, str]


def coded_passage_projections(
    db: Session,
    *,
    organisation_id: int,
    study_ids: list[int],
    code_ids: set[int] | None = None,
    limit: int = 5000,
) -> tuple[list[CodedPassageProjection], bool]:
    """Load a bounded tenant/study projection without persisting source text."""
    if not study_ids:
        return [], False
    safe_limit = min(max(limit, 1), 5000)
    statement = (
        select(
            CodeApplication,
            AnalysisTarget,
            ActivityResponse,
            Participant,
            ResearchCode,
            User,
            Activity,
        )
        .join(AnalysisTarget, AnalysisTarget.id == CodeApplication.analysis_target_id)
        .join(
            ActivityResponse, ActivityResponse.id == AnalysisTarget.activity_response_id
        )
        .join(Participant, Participant.id == ActivityResponse.participant_id)
        .join(ResearchCode, ResearchCode.id == CodeApplication.research_code_id)
        .join(User, User.id == CodeApplication.applied_by_id)
        .join(Activity, Activity.id == ActivityResponse.activity_id)
        .where(
            CodeApplication.organisation_id == organisation_id,
            CodeApplication.study_id.in_(study_ids),
            AnalysisTarget.organisation_id == organisation_id,
            AnalysisTarget.study_id.in_(study_ids),
            AnalysisTarget.target_type == "activity_response",
            ActivityResponse.organisation_id == organisation_id,
            ActivityResponse.study_id.in_(study_ids),
            Participant.organisation_id == organisation_id,
            ResearchCode.organisation_id == organisation_id,
            ResearchCode.study_id.in_(study_ids),
            User.organisation_id == organisation_id,
            Activity.organisation_id == organisation_id,
            Activity.study_id.in_(study_ids),
        )
    )
    if code_ids is not None:
        if not code_ids:
            return [], False
        statement = statement.where(CodeApplication.research_code_id.in_(code_ids))
    rows = db.execute(
        statement.order_by(CodeApplication.created_at, CodeApplication.id).limit(
            safe_limit + 1
        )
    ).all()
    truncated = len(rows) > safe_limit
    output = []
    for application, target, response, participant, code, researcher, activity in rows[
        :safe_limit
    ]:
        text = response_body(response.value_json)
        output.append(
            CodedPassageProjection(
                application=application,
                target=target,
                response=response,
                participant=participant,
                code=code,
                researcher=researcher,
                activity=activity,
                passage=verified_passage(text, application.anchor_json),
                response_text=text,
                context=response_context(response.value_json),
            )
        )
    return output, truncated
