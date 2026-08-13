from types import SimpleNamespace

import pytest

from app.evidence_explorer import evidence_items, filter_evidence
from app.research_intelligence import (
    UnsafeAIResponse,
    build_evidence_confidence,
    create_confidence_assessment,
    create_suggestion,
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


def valid_output():
    return {"suggested_codes": [{"label": "queue", "evidence": "phone queue"}], "provisional_insight": "Access barrier", "confidence": 0.7, "needs_researcher_review": True}


def test_gated_suggestion_and_review_preserve_source_traceability():
    db, user, study, response = fixtures()
    row = create_suggestion(db, user, study, response, valid_output())
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
    row = create_suggestion(db, user, study, response, valid_output())
    user.role = "observer"
    with pytest.raises(PermissionError):
        review_suggestion(user, row, "accepted")


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
