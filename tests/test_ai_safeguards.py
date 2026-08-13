import pytest
from app.ai_safeguards import SafeguardViolation, validate_confidence, validate_provisional_ai_output, validate_scope

SOURCE = "I cannot attend appointments during standard working hours."
GOOD = {"needs_researcher_review": True, "status": "awaiting_researcher_review", "suggested_codes": [{"label": "access", "evidence": "I cannot attend appointments during standard working hours."}], "provisional_insight": "An access concern requires researcher review."}

def test_review_gate_and_exact_quote_are_required():
    validate_provisional_ai_output(GOOD, SOURCE)
    for update in ({"needs_researcher_review": False}, {"status": "accepted"}, {"suggested_codes": [{"label":"x","evidence":"invented quote"}]}, {"provisional_insight":"This proves causation."}):
        candidate = {**GOOD, **update}
        with pytest.raises(SafeguardViolation): validate_provisional_ai_output(candidate, SOURCE)

def test_scope_is_mandatory_and_cross_scope_is_rejected():
    validate_scope(1, 2, [{"organisation_id":1,"study_id":2}])
    with pytest.raises(SafeguardViolation): validate_scope(None, 2, [])
    with pytest.raises(SafeguardViolation): validate_scope(1, 2, [{"organisation_id":2,"study_id":2}])

def test_confidence_preserves_negative_cases_and_no_pseudo_precision():
    validate_confidence("developing", {1}, [])
    validate_confidence("contested", {1,2}, [9])
    for category, participants, contradictions in (("strong", {1}, []), ("moderate", {1,2}, [9]), ("87%", {1,2}, [])):
        with pytest.raises(SafeguardViolation): validate_confidence(category, participants, contradictions)
