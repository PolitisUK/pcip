from types import SimpleNamespace

import pytest

from app.evidence_explorer import evidence_items, filter_evidence
from app.theme_explorer import create_theme, parse_suggestion_ids
from app.research_intelligence import (
    UnsafeAIResponse,
    build_evidence_confidence,
    create_confidence_assessment,
    create_suggestion,
    retrieve_grounded_context,
    review_suggestion,
)


class FakeDb:
    def add(self, row):
        self.row = row


def fixtures():
    user = SimpleNamespace(id=7, organisation_id=3, role="researcher")
    study = SimpleNamespace(id=11)
    response = SimpleNamespace(id=19, organisation_id=3, study_id=11, value_json='{"text":"The phone queue disconnected before I spoke to an adviser."}')
    return FakeDb(), user, study, response


def methodology_configuration(**overrides):
    values = {
        "primary_methodology_id": "M08",
        "methodology_variant": "inductive",
        "library_version": "1.0.0",
        "protocol_version": "protocol-v1",
        "ai_enabled": True,
        "allowed_ai_tasks_json": '["candidate_code_suggestions", "retrieval"]',
        "researcher_confirmed_at": object(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def valid_output():
    return {"suggested_codes": [{"label": "queue", "evidence": "phone queue"}], "provisional_insight": "Access barrier", "confidence": 0.7, "needs_researcher_review": True}


def test_gated_suggestion_and_review_preserve_source_traceability():
    db, user, study, response = fixtures()
    row = create_suggestion(db, user, study, response, valid_output(), methodology_configuration())
    assert row.status == "awaiting_researcher_review"
    assert "phone queue" in row.source_snapshot
    review_suggestion(user, row, "accepted")
    assert row.reviewer_user_id == user.id


def test_missing_gate_rejected():
    db, user, study, response = fixtures()
    with pytest.raises(UnsafeAIResponse):
        create_suggestion(db, user, study, response, {"suggested_codes": [], "provisional_insight": "x"})


def test_participant_or_cross_scope_actor_rejected():
    db, user, study, response = fixtures()
    row = create_suggestion(db, user, study, response, valid_output(), methodology_configuration())
    user.role = "observer"
    with pytest.raises(PermissionError):
        review_suggestion(user, row, "accepted")


def test_ai_suggestion_requires_confirmed_method_and_preserves_method_provenance():
    db, user, study, response = fixtures()
    with pytest.raises(UnsafeAIResponse, match="confirm"):
        create_suggestion(db, user, study, response, valid_output())
    row = create_suggestion(db, user, study, response, valid_output(), methodology_configuration())
    assert row.methodology_id == "M08"
    assert row.methodology_library_version == "1.0.0"
    assert "E01" in row.methodology_rule_references_json


def test_method_gate_blocks_incompatible_reflexive_reliability_operation():
    from app.methodology import MethodologyGateViolation, study_grounding

    with pytest.raises(MethodologyGateViolation):
        study_grounding(methodology_configuration(allowed_ai_tasks_json='["coding_reliability"]'), "coding_reliability")


def test_cross_study_methodology_configuration_is_rejected():
    db, user, study, response = fixtures()
    with pytest.raises(PermissionError, match="configuration scope"):
        create_suggestion(
            db, user, study, response, valid_output(),
            methodology_configuration(study_id=study.id + 1, organisation_id=user.organisation_id),
        )


def test_retrieval_is_limited_to_authorised_study_evidence():
    db, user, study, response = fixtures()
    context = retrieve_grounded_context(user, study, methodology_configuration(), [response])
    assert context["evidence_ids"] == (response.id,)
    assert context["grounding"].methodology_id == "M08"
    other_study_response = SimpleNamespace(**vars(response))
    other_study_response.study_id = study.id + 1
    with pytest.raises(PermissionError, match="Evidence scope"):
        retrieve_grounded_context(user, study, methodology_configuration(), [other_study_response])


def source(identifier, participant):
    return SimpleNamespace(id=identifier, participant_id=participant, organisation_id=3, study_id=11)


def test_confidence_is_qualitative_and_contradictions_are_contested():
    result = build_evidence_confidence("Appointment access", [source(1, 1), source(2, 2)], [source(3, 3)])
    assert result["category"] == "contested"
    assert result["contradiction_ids"] == [3]
    assert "not a measure of prevalence" in result["limitations"][0]


def test_one_account_does_not_become_strong_evidence():
    result = build_evidence_confidence("Appointment access", [source(1, 1), source(2, 1)], [])
    assert result["category"] == "developing"
    assert "one participant" in result["limitations"][-1]


def test_confidence_assessment_enforces_scope_and_review_gate():
    db, user, study, _ = fixtures()
    row = create_confidence_assessment(db, user, study, "Access", [source(1, 1)], [])
    assert row.status == "awaiting_researcher_review"
    assert row.category == "developing"
    outsider = source(9, 9); outsider.organisation_id = 4
    with pytest.raises(PermissionError):
        create_confidence_assessment(db, user, study, "Access", [outsider], [])
    user.role = "researcher"
    user.organisation_id = 99
    with pytest.raises(PermissionError):
        review_suggestion(user, row, "accepted")


def test_evidence_explorer_keeps_quotes_verbatim_and_filters_ai_labels_separately():
    response = SimpleNamespace(
        id=19,
        participant_id=4,
        activity_id=8,
        value_json='{"text":"The bus stop has no shelter when it rains."}',
        submitted_at=None,
        updated_at=__import__("datetime").datetime.now(),
    )
    activity = SimpleNamespace(id=8, title="Travel diary")
    participant = SimpleNamespace(id=4, reference="P-004")
    suggestion = SimpleNamespace(
        source_response_id=19,
        status="awaiting_researcher_review",
        suggested_codes_json='[{"label":"accessibility","evidence":"bus stop"}]',
    )
    items = evidence_items([response], activities={8: activity}, participants={4: participant}, suggestions=[suggestion])
    assert items[0].source_excerpt == "The bus stop has no shelter when it rains."
    assert items[0].analysis_status == "awaiting_researcher_review"
    assert filter_evidence(items, code="Accessibility") == items
    assert filter_evidence(items, query="shelter rain") == items


def test_researcher_theme_requires_accepted_analysis_in_its_study():
    db, user, study, _ = fixtures()
    accepted = SimpleNamespace(id=21, organisation_id=3, study_id=11, status="accepted")
    theme = create_theme(db, user, study, name="Access barriers", description="Working interpretation", suggestions=[accepted])
    assert theme.status == "researcher_draft"
    assert theme.source_suggestion_ids_json == "[21]"
    assert parse_suggestion_ids("21, 22") == {21, 22}
    accepted.status = "awaiting_researcher_review"
    with pytest.raises(PermissionError):
        create_theme(db, user, study, name="Unsafe", description="", suggestions=[accepted])
