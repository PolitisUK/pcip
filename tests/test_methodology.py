from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.config import Settings, validate_runtime_settings
from app.methodology import MethodologyGateViolation, get_methodology, library_records, methodology_library, source_metadata, structured_companions, study_grounding, validate_configuration


def confirmed_configuration(**overrides):
    values = {
        "primary_methodology_id": "M11",
        "methodology_variant": "framework_method",
        "research_design": "not_specified",
        "analysis_approaches_json": '["framework_analysis"]',
        "library_version": "1.0.0",
        "protocol_version": "protocol-v2",
        "ai_enabled": True,
        "allowed_ai_tasks_json": '["retrieval", "matrix_organisation"]',
        "researcher_confirmed_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_published_library_has_stable_source_provenance_and_method_profiles():
    library = methodology_library()
    assert library["publication_state"] == "PUBLISHED"
    assert library["source_bundle"]["methodology_synthesis_report.md"].startswith("sha256:")
    assert get_methodology("M08")["name"] == "Reflexive thematic analysis"
    assert get_methodology("M13")["disallowed_ai_tasks"]
    assert source_metadata(("E01",))[0]["identifier"] == "10.1191/1478088706qp063oa"
    assert len(library_records()) == 27
    assert {"knowledge", "claims", "disagreements"} == set(structured_companions())


@pytest.mark.parametrize(
    ("methodology_id", "task", "research_design", "analysis_approaches_json"),
    [
        ("M08", "coding_reliability", "not_specified", '["reflexive_thematic"]'),
        ("M13", "candidate_code_suggestions", "not_specified", '["conversation_analysis"]'),
        ("M15", "frequency_claim", "phenomenological", "[]"),
        ("M20", "governance_decision", "participatory_action", "[]"),
    ],
)
def test_method_specific_gates_do_not_universalise_incompatible_operations(methodology_id, task, research_design, analysis_approaches_json):
    with pytest.raises(MethodologyGateViolation):
        study_grounding(confirmed_configuration(
            primary_methodology_id=methodology_id,
            research_design=research_design,
            analysis_approaches_json=analysis_approaches_json,
            allowed_ai_tasks_json=f'["{task}"]',
        ), task)


def test_legacy_controlled_id_cannot_ground_ai_without_current_canonical_mapping():
    with pytest.raises(MethodologyGateViolation, match="current study design"):
        study_grounding(confirmed_configuration(
            primary_methodology_id="M08",
            research_design="not_specified",
            analysis_approaches_json="[]",
            allowed_ai_tasks_json='["retrieval"]',
        ), "retrieval")


def test_configuration_requires_researcher_confirmation_and_protocol():
    issues = validate_configuration(
        primary_methodology_id="M08", methodology_variant="inductive", secondary_methodologies=[],
        research_questions="", protocol_reference="", protocol_version="", sampling_approach="", data_collection_plan="",
        ai_enabled=True, allowed_ai_tasks=["candidate_code_suggestions"], researcher_confirmation=False,
    )
    assert any("required" in issue.lower() for issue in issues)
    assert any("researcher" in issue.lower() for issue in issues)


def test_configuration_marks_reflexive_reliability_conflict_for_review():
    issues = validate_configuration(
        primary_methodology_id="M08", methodology_variant="inductive", secondary_methodologies=[],
        research_questions="How is access experienced?", protocol_reference="protocol-1", protocol_version="1",
        sampling_approach="Information-rich purposive sample", data_collection_plan="Interviews", ai_enabled=True,
        allowed_ai_tasks=["coding_reliability"], researcher_confirmation=True,
    )
    assert any("METHODOLOGICAL REVIEW REQUIRED" in issue for issue in issues)


def test_training_and_cross_customer_flags_fail_closed_even_in_development():
    candidate = Settings(participant_training_allowed=True)
    with pytest.raises(RuntimeError, match="training"):
        validate_runtime_settings(candidate)
