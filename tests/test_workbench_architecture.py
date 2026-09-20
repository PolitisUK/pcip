import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.analysis_canvas import (
    add_canvas_node,
    canvas_candidates,
    move_canvas_node,
)
from app.advanced_queries import AdvancedQueryFilters, advanced_query
from app.analysis_lifecycle import remove_analytical_references
from app.analysis_objects import resolve_analytical_object
from app.analysis_projections import coded_passage_projections
from app.analysis_router import ANALYSIS_GET_ROUTES, include_analysis_router
from app.db import Base
from app.models import (
    Activity,
    ActivityResponse,
    AnalysisCanvasNode,
    AnalysisTarget,
    AnalyticalRelationship,
    CodeApplication,
    Organisation,
    Participant,
    Project,
    ResearchCode,
    ResearchTheme,
    ResearchThemeCode,
    Study,
    StudyEnrolment,
    User,
)
from app.passage_coding import text_anchor
from app.relationships import create_relationship


@pytest.fixture
def analysis_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                Organisation(id=1, name="Alpha", slug="alpha"),
                Organisation(id=2, name="Beta", slug="beta"),
                User(
                    id=1,
                    organisation_id=1,
                    name="Researcher",
                    email="researcher@example.test",
                ),
                User(id=2, organisation_id=2, name="Other", email="other@example.test"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Project(
                    id=1, organisation_id=1, title="Project", code="P1", created_by_id=1
                ),
                Project(
                    id=2, organisation_id=2, title="Other", code="P2", created_by_id=2
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                Study(
                    id=1,
                    organisation_id=1,
                    project_id=1,
                    title="Study",
                    code="S1",
                    created_by_id=1,
                ),
                Study(
                    id=2,
                    organisation_id=2,
                    project_id=2,
                    title="Other",
                    code="S2",
                    created_by_id=2,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                Participant(
                    id=1,
                    organisation_id=1,
                    reference="P-001",
                    name="Person",
                    created_by_id=1,
                ),
                Participant(
                    id=2,
                    organisation_id=2,
                    reference="P-002",
                    name="Other",
                    created_by_id=2,
                ),
                Activity(id=1, organisation_id=1, study_id=1, title="Diary"),
                Activity(id=2, organisation_id=2, study_id=2, title="Other diary"),
                ResearchCode(
                    id=1,
                    organisation_id=1,
                    study_id=1,
                    name="Access",
                    definition="Barriers",
                    created_by_id=1,
                ),
                ResearchCode(
                    id=2,
                    organisation_id=2,
                    study_id=2,
                    name="Foreign",
                    definition="Unavailable",
                    created_by_id=2,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                StudyEnrolment(organisation_id=1, study_id=1, participant_id=1),
                StudyEnrolment(organisation_id=2, study_id=2, participant_id=2),
                ActivityResponse(
                    id=1,
                    organisation_id=1,
                    study_id=1,
                    activity_id=1,
                    participant_id=1,
                    value_json=json.dumps(
                        {"answer": "Before 😀 after", "place": "Clinic"}
                    ),
                    status="submitted",
                ),
                ActivityResponse(
                    id=2,
                    organisation_id=2,
                    study_id=2,
                    activity_id=2,
                    participant_id=2,
                    value_json=json.dumps({"answer": "Foreign response"}),
                    status="submitted",
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                AnalysisTarget(
                    id=1,
                    organisation_id=1,
                    study_id=1,
                    target_type="activity_response",
                    activity_response_id=1,
                    created_by_id=1,
                ),
                AnalysisTarget(
                    id=2,
                    organisation_id=2,
                    study_id=2,
                    target_type="activity_response",
                    activity_response_id=2,
                    created_by_id=2,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                CodeApplication(
                    id=1,
                    organisation_id=1,
                    study_id=1,
                    analysis_target_id=1,
                    research_code_id=1,
                    applied_by_id=1,
                    anchor_json=text_anchor("Before 😀 after", 7, 8),
                ),
                CodeApplication(
                    id=2,
                    organisation_id=2,
                    study_id=2,
                    analysis_target_id=2,
                    research_code_id=2,
                    applied_by_id=2,
                    anchor_json=text_anchor("Foreign response", 0, 7),
                ),
            ]
        )
        db.commit()
        yield db


def test_typed_object_resolver_enforces_tenant_study_and_bounds(analysis_session):
    user = analysis_session.get(User, 1)
    code = resolve_analytical_object(
        analysis_session,
        user,
        study_id=1,
        object_type="code",
        object_id=1,
        require_edit=True,
    )
    assert code is not None
    assert (code.label, code.summary, code.navigation_url, code.editable) == (
        "Access",
        "Barriers",
        "/studies/1/codebook",
        True,
    )
    participant = resolve_analytical_object(
        analysis_session, user, study_id=1, object_type="participant_case", object_id=1
    )
    assert participant is not None and participant.label == "P-001 · Person"
    assert (
        resolve_analytical_object(
            analysis_session, user, study_id=2, object_type="code", object_id=2
        )
        is None
    )
    assert (
        resolve_analytical_object(
            analysis_session, user, study_id=1, object_type="users", object_id=1
        )
        is None
    )


def test_shared_projection_is_scoped_traceable_and_unicode_safe(analysis_session):
    rows, truncated = coded_passage_projections(
        analysis_session, organisation_id=1, study_ids=[1], code_ids={1}
    )
    assert not truncated and len(rows) == 1
    projection = rows[0]
    assert projection.passage == "😀"
    assert projection.response_text == "Before 😀 after"
    assert projection.context == {"place": "Clinic"}
    assert projection.participant.reference == "P-001"
    assert projection.researcher.id == 1
    assert coded_passage_projections(
        analysis_session, organisation_id=1, study_ids=[2]
    ) == ([], False)
    assert coded_passage_projections(
        analysis_session, organisation_id=1, study_ids=[1], code_ids=set()
    ) == ([], False)


def test_advanced_query_boolean_theme_relationship_and_cooccurrence(analysis_session):
    user = analysis_session.get(User, 1)
    second_code = ResearchCode(
        id=3,
        organisation_id=1,
        study_id=1,
        name="Trust",
        definition="Institutional trust",
        created_by_id=1,
    )
    theme = ResearchTheme(
        id=1,
        organisation_id=1,
        study_id=1,
        name="Service relationship",
        description="Researcher interpretation",
        source_suggestion_ids_json="[]",
        status="researcher_draft",
        created_by_id=1,
    )
    analysis_session.add_all([second_code, theme])
    analysis_session.flush()
    second_application = CodeApplication(
        id=3,
        organisation_id=1,
        study_id=1,
        analysis_target_id=1,
        research_code_id=second_code.id,
        applied_by_id=1,
        anchor_json=text_anchor("Before 😀 after", 0, 6),
    )
    analysis_session.add_all(
        [
            second_application,
            ResearchThemeCode(
                organisation_id=1,
                study_id=1,
                research_theme_id=theme.id,
                research_code_id=second_code.id,
                linked_by_id=1,
            ),
            AnalyticalRelationship(
                organisation_id=1,
                study_id=1,
                source_type="code",
                source_id=second_code.id,
                relationship_type="contradicts",
                target_type="code_application",
                target_id=1,
                rationale="Negative case comparison",
                created_by_id=1,
            ),
        ]
    )
    analysis_session.commit()

    combined = advanced_query(
        analysis_session,
        user,
        AdvancedQueryFilters(
            study_ids=(1,), include_code_ids=frozenset({1, 3}), operator="and"
        ),
    )
    assert combined.total_applications == 2
    assert (combined.participant_cases, combined.source_entries) == (1, 1)
    pair = combined.co_occurrences[0]
    assert (
        pair.left_code_id,
        pair.right_code_id,
        pair.source_entries,
        pair.participant_cases,
    ) == (1, 3, 1, 1)
    assert {item.passage for item in combined.results} == {"😀", "Before"}

    excluded = advanced_query(
        analysis_session,
        user,
        AdvancedQueryFilters(
            study_ids=(1,),
            include_code_ids=frozenset({1}),
            exclude_code_ids=frozenset({3}),
        ),
    )
    assert excluded.total_applications == 0
    themed = advanced_query(
        analysis_session,
        user,
        AdvancedQueryFilters(study_ids=(1,), theme_id=theme.id),
    )
    assert [item.code.id for item in themed.results] == [3]
    any_code = advanced_query(
        analysis_session,
        user,
        AdvancedQueryFilters(
            study_ids=(1,), include_code_ids=frozenset({1, 999}), operator="or"
        ),
    )
    assert [item.code.id for item in any_code.results] == [1]
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert advanced_query(
        analysis_session,
        user,
        AdvancedQueryFilters(study_ids=(1,), date_from=future),
    ).total_applications == 0
    contradictory = advanced_query(
        analysis_session,
        user,
        AdvancedQueryFilters(study_ids=(1,), relationship_type="contradicts"),
    )
    assert {item.application.id for item in contradictory.results} == {1, 3}
    assert advanced_query(
        analysis_session, user, AdvancedQueryFilters(study_ids=(2,))
    ).total_applications == 0


def test_relationship_service_uses_scoped_object_resolution(analysis_session):
    user = analysis_session.get(User, 1)
    relationship = create_relationship(
        analysis_session,
        user,
        study_id=1,
        source_ref="analysis_target:1",
        relationship_type="supports",
        target_ref="code:1",
        rationale="Traceable link",
    )
    analysis_session.flush()
    assert relationship.organisation_id == 1
    resolved = resolve_analytical_object(
        analysis_session,
        user,
        study_id=1,
        object_type="relationship",
        object_id=relationship.id,
    )
    assert resolved is not None
    assert resolved.navigation_url == "/studies/1/relationships"
    assert "supports" in resolved.summary
    with pytest.raises(ValueError, match="unavailable"):
        create_relationship(
            analysis_session,
            user,
            study_id=1,
            source_ref="analysis_target:1",
            relationship_type="supports",
            target_ref="code:2",
            rationale="Forged cross-tenant link",
        )


def test_lifecycle_hook_removes_all_requested_relationship_references(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.analysis_lifecycle.remove_object_relationships",
        lambda db, object_type, identifiers: calls.append(
            (db, object_type, identifiers)
        ),
    )
    class Marker:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)

    marker = Marker()
    remove_analytical_references(
        marker, {"code": {3}, "memo": set(), "annotation": {7, 8}}
    )
    assert calls == [(marker, "code", {3}), (marker, "annotation", {7, 8})]
    assert len(marker.statements) == 2


def test_canvas_layout_uses_scoped_objects_and_keeps_source_authoritative(
    analysis_session,
):
    user = analysis_session.get(User, 1)
    candidates = canvas_candidates(analysis_session, user, 1)
    coded = next(item for item in candidates if item.object_type == "code_application")
    assert coded.label == "Coded passage · Access"
    assert coded.summary == "😀"

    node = add_canvas_node(
        analysis_session, user, study_id=1, object_ref="code_application:1"
    )
    analysis_session.flush()
    assert (node.organisation_id, node.study_id, node.object_type, node.object_id) == (
        1,
        1,
        "code_application",
        1,
    )
    assert not hasattr(node, "participant_text")
    moved = move_canvas_node(
        analysis_session,
        user,
        study_id=1,
        node_id=node.id,
        x=5000,
        y=-20,
    )
    assert (moved.x, moved.y) == (4000.0, 0.0)
    with pytest.raises(PermissionError, match="unavailable"):
        add_canvas_node(analysis_session, user, study_id=1, object_ref="code:2")

    remove_analytical_references(analysis_session, {"code_application": {1}})
    analysis_session.flush()
    assert analysis_session.get(AnalysisCanvasNode, node.id) is None


def test_analysis_router_owns_each_registered_get_route_once():
    app = FastAPI()

    def endpoint():
        return "ok"

    include_analysis_router(app, {name: endpoint for _, name in ANALYSIS_GET_ROUTES})
    included = app.routes[-1].original_router
    registered_paths = [route.path for route in included.routes]
    for path, _ in ANALYSIS_GET_ROUTES:
        assert registered_paths.count(path) == 1
    assert all("analysis-workbench" in route.tags for route in included.routes)
