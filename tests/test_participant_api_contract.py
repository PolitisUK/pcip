from pathlib import Path
from typing import get_args

import yaml

from app.participant_api.schemas import (
    ActivitySummary,
    AvailableStudyListResponse,
    BearerSession,
    InvitationContext,
    ParticipantSummary,
    ParticipantSessionResponse,
    SessionInfo,
    SessionExchangeResponse,
    SessionSwitchRequest,
    SubmissionEvidenceItem,
    SubmissionHistoryItem,
    SubmissionHistoryResponse,
    EntryLocation,
    DraftResponseRequest,
    ActivityResponseValue,
)


CONTRACT_PATH = Path(__file__).parents[1] / "docs" / "participant-api-v1.yaml"


def _contract_schema(name: str) -> dict:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    return contract["components"]["schemas"][name]


def test_session_contract_matches_backend_response_models():
    invitation = _contract_schema("InvitationContext")
    participant = _contract_schema("ParticipantSummary")
    bearer_session = _contract_schema("BearerSession")
    exchange = _contract_schema("SessionExchangeResponse")
    session = _contract_schema("ParticipantSessionResponse")
    available_studies = _contract_schema("AvailableStudyListResponse")
    switch_request = _contract_schema("SessionSwitchRequest")

    assert set(invitation["properties"]) == set(InvitationContext.model_fields)
    assert set(invitation["required"]) == set(InvitationContext.model_fields)
    assert invitation["properties"]["invitation_status"]["enum"] == list(
        get_args(InvitationContext.model_fields["invitation_status"].annotation)
    )
    assert set(participant["properties"]) == set(ParticipantSummary.model_fields)
    assert set(bearer_session["properties"]) == set(BearerSession.model_fields)

    assert set(exchange["properties"]) == set(SessionExchangeResponse.model_fields)
    assert set(exchange["required"]) == set(SessionExchangeResponse.model_fields)
    assert set(session["properties"]) == set(ParticipantSessionResponse.model_fields)
    assert set(session["required"]) == set(ParticipantSessionResponse.model_fields)
    assert set(session["properties"]["session"]["properties"]) == set(SessionInfo.model_fields)
    assert set(available_studies["properties"]) == set(AvailableStudyListResponse.model_fields)
    assert set(available_studies["required"]) == set(AvailableStudyListResponse.model_fields)
    assert set(switch_request["properties"]) == set(SessionSwitchRequest.model_fields)
    assert set(switch_request["required"]) == set(SessionSwitchRequest.model_fields)

    expected_next_actions = list(
        get_args(ParticipantSessionResponse.model_fields["next_action"].annotation)
    )
    assert exchange["properties"]["next_action"]["enum"] == expected_next_actions
    assert session["properties"]["next_action"]["enum"] == expected_next_actions


def test_session_paths_reference_the_matching_response_schemas():
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    paths = contract["paths"]

    exchange_schema = paths["/api/v1/participant/session/exchange"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    session_schema = paths["/api/v1/participant/session"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    available_studies_schema = paths["/api/v1/participant/session/available-studies"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    switch_request_schema = paths["/api/v1/participant/session/switch"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    switch_schema = paths["/api/v1/participant/session/switch"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert exchange_schema == {"$ref": "#/components/schemas/SessionExchangeResponse"}
    assert session_schema == {"$ref": "#/components/schemas/ParticipantSessionResponse"}
    assert available_studies_schema == {"$ref": "#/components/schemas/AvailableStudyListResponse"}
    assert switch_request_schema == {"$ref": "#/components/schemas/SessionSwitchRequest"}
    assert switch_schema == {"$ref": "#/components/schemas/SessionExchangeResponse"}


def test_submission_history_contract_matches_backend_response_models():
    evidence = _contract_schema("SubmissionEvidenceItem")
    item = _contract_schema("SubmissionHistoryItem")
    response = _contract_schema("SubmissionHistoryResponse")

    assert set(evidence["properties"]) == set(SubmissionEvidenceItem.model_fields)
    assert set(evidence["required"]) == set(SubmissionEvidenceItem.model_fields)
    assert set(item["properties"]) == set(SubmissionHistoryItem.model_fields)
    assert set(item["required"]) == set(SubmissionHistoryItem.model_fields)
    assert set(response["properties"]) == set(SubmissionHistoryResponse.model_fields)
    assert set(response["required"]) == set(SubmissionHistoryResponse.model_fields)

    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    schema = contract["paths"]["/api/v1/participant/submissions"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/SubmissionHistoryResponse"}


def test_activity_contract_includes_repeatable_entry_semantics():
    activity = _contract_schema("ActivitySummary")
    assert set(activity["properties"]) == set(ActivitySummary.model_fields)
    assert activity["properties"]["allow_multiple_entries"]["type"] == "boolean"
    assert activity["properties"]["submitted_entry_count"]["type"] == "integer"
    assert activity["properties"]["submitted_entry_count"]["minimum"] == 0
    assert activity["properties"]["allow_participant_location"]["type"] == "boolean"


def test_location_contract_matches_the_strict_backend_models():
    location = _contract_schema("EntryLocation")
    draft = _contract_schema("DraftResponseRequest")
    value = _contract_schema("ActivityResponseValue")

    assert set(location["properties"]) == set(EntryLocation.model_fields)
    assert set(location["required"]) == set(EntryLocation.model_fields)
    assert draft["properties"]["location"] == {"$ref": "#/components/schemas/EntryLocation"}
    assert value["properties"]["location"] == {"$ref": "#/components/schemas/EntryLocation"}
    assert "location" in DraftResponseRequest.model_fields
    assert "location" in ActivityResponseValue.model_fields
