from types import SimpleNamespace

import pytest

from app.research_intelligence import (
    UnsafeAIResponse,
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
    user.role = "researcher"
    user.organisation_id = 99
    with pytest.raises(PermissionError):
        review_suggestion(user, row, "accepted")
