from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from scripts.set_research_intelligence_enabled import (
    ResearchIntelligenceConfigurationError,
    set_research_intelligence_enabled,
)

RELEASE_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
HOSTNAME = "production.example.test"


class OperationState:
    def __init__(self, enabled: str | None = "false"):
        self.settings = {
            "RUN_MIGRATIONS": "false",
            "SEED_DEMO_DATA": "false",
            "RUN_RIVERMERE_PRODUCTION_DEMO_SEED": "false",
            "UNRELATED_SECRET": "must-be-preserved",
        }
        if enabled is not None:
            self.settings["RESEARCH_INTELLIGENCE_ENABLED"] = enabled
        self.release_shas = [RELEASE_SHA]
        self.image_digests = [IMAGE_DIGEST]
        self.revisions = ["0035"]
        self.put_payloads: list[dict] = []
        self.public_paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "management.azure.com":
            if request.method == "GET" and "/config/" not in request.url.path:
                digest = self.image_digests.pop(0) if len(self.image_digests) > 1 else self.image_digests[0]
                return httpx.Response(
                    200,
                    json={
                        "properties": {
                            "defaultHostName": HOSTNAME,
                            "siteConfig": {"linuxFxVersion": f"DOCKER|registry/pcip@{digest}"},
                        }
                    },
                )
            if request.method == "POST" and request.url.path.endswith("/config/appsettings/list"):
                return httpx.Response(200, json={"properties": dict(self.settings)})
            if request.method == "PUT" and request.url.path.endswith("/config/appsettings"):
                payload = json.loads(request.content)
                self.put_payloads.append(payload)
                self.settings = dict(payload["properties"])
                return httpx.Response(200, json={"properties": dict(self.settings)})
        if request.url.host == HOSTNAME and request.url.path == "/health/ready":
            release = self.release_shas.pop(0) if len(self.release_shas) > 1 else self.release_shas[0]
            return httpx.Response(200, json={"status": "ready", "revision": release})
        if request.url.host == HOSTNAME and request.url.path in {"/", "/privacy", "/terms"}:
            self.public_paths.append(request.url.path)
            return httpx.Response(200, text="ok")
        return httpx.Response(404)

    def revision_lookup(self):
        revision = self.revisions.pop(0) if len(self.revisions) > 1 else self.revisions[0]
        return SimpleNamespace(approved_result=lambda: {"alembic_revision": revision})


def environment() -> dict[str, str]:
    return {
        "AZURE_SUBSCRIPTION_ID": "11111111-1111-1111-1111-111111111111",
        "AZURE_RESOURCE_GROUP": "rg-pcip-prod",
        "PCIP_PRODUCTION_APP": "citizencentric-pcip-prod",
    }


def execute(state: OperationState, enabled: bool):
    with httpx.Client(transport=httpx.MockTransport(state.handler)) as client:
        return set_research_intelligence_enabled(
            enabled,
            environ=environment(),
            client=client,
            token="fixed-worker-token",
            revision_lookup=state.revision_lookup,
            wait=lambda _seconds: None,
        )


@pytest.mark.parametrize(("prior", "requested"), [("false", True), ("true", False)])
def test_fixed_operation_changes_only_research_intelligence(prior, requested):
    state = OperationState(prior)
    before = dict(state.settings)

    result = execute(state, requested)

    assert len(state.put_payloads) == 1
    written = state.put_payloads[0]["properties"]
    assert written["RESEARCH_INTELLIGENCE_ENABLED"] == str(requested).lower()
    assert {key: value for key, value in written.items() if key != "RESEARCH_INTELLIGENCE_ENABLED"} == {
        key: value for key, value in before.items() if key != "RESEARCH_INTELLIGENCE_ENABLED"
    }
    assert result.prior_value is (prior == "true")
    assert result.requested_value is requested
    assert result.effective_value is requested
    assert result.readiness_status == "ready"
    assert result.release_sha == RELEASE_SHA
    assert result.image_digest == IMAGE_DIGEST
    assert result.alembic_revision == "0035"
    assert state.public_paths == ["/", "/privacy", "/terms"]


@pytest.mark.parametrize("enabled", [False, True])
def test_same_value_request_is_idempotent(enabled):
    state = OperationState(str(enabled).lower())

    result = execute(state, enabled)

    assert state.put_payloads == []
    assert result.prior_value is enabled
    assert result.effective_value is enabled


def test_absent_setting_is_safely_idempotent_false():
    state = OperationState(None)
    result = execute(state, False)
    assert state.put_payloads == []
    assert result.prior_value is False
    assert result.effective_value is False


def test_non_boolean_request_is_rejected_before_azure_access():
    state = OperationState()
    with (
        httpx.Client(transport=httpx.MockTransport(state.handler)) as client,
        pytest.raises(ResearchIntelligenceConfigurationError, match="must be boolean"),
    ):
        set_research_intelligence_enabled(  # type: ignore[arg-type]
            "true",
            environ=environment(),
            client=client,
            token="fixed-worker-token",
        )
    assert state.put_payloads == []


def test_release_revision_drift_fails_closed():
    state = OperationState("false")
    state.release_shas = [RELEASE_SHA, "c" * 40]
    with pytest.raises(ResearchIntelligenceConfigurationError, match="release changed"):
        execute(state, True)


def test_image_digest_drift_fails_closed():
    state = OperationState("false")
    state.image_digests = [IMAGE_DIGEST, "sha256:" + "c" * 64]
    with pytest.raises(ResearchIntelligenceConfigurationError, match="image changed"):
        execute(state, True)


def test_alembic_revision_drift_fails_closed():
    state = OperationState("false")
    state.revisions = ["0035", "0036"]
    with pytest.raises(ResearchIntelligenceConfigurationError, match="Alembic revision changed"):
        execute(state, True)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RUN_MIGRATIONS", "true"),
        ("SEED_DEMO_DATA", "true"),
        ("RUN_RIVERMERE_PRODUCTION_DEMO_SEED", "true"),
        ("RUN_RIVERMERE_DEMO_SEED", "true"),
    ],
)
def test_migration_or_seeding_safety_drift_fails_before_write(name, value):
    state = OperationState("false")
    state.settings[name] = value
    with pytest.raises(ResearchIntelligenceConfigurationError, match="safety setting"):
        execute(state, True)
    assert state.put_payloads == []


@pytest.mark.parametrize(
    "name",
    [
        "RUN_MIGRATIONS",
        "SEED_DEMO_DATA",
        "RUN_RIVERMERE_PRODUCTION_DEMO_SEED",
        "RUN_RIVERMERE_DEMO_SEED",
    ],
)
def test_migration_or_seeding_safety_drift_after_write_fails_closed(name):
    state = OperationState("false")
    original_handler = state.handler

    def handler(request: httpx.Request) -> httpx.Response:
        response = original_handler(request)
        if request.method == "PUT":
            state.settings[name] = "true"
        return response

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ResearchIntelligenceConfigurationError, match="safety setting"),
    ):
        set_research_intelligence_enabled(
            True,
            environ=environment(),
            client=client,
            token="fixed-worker-token",
            revision_lookup=state.revision_lookup,
            wait=lambda _seconds: None,
        )


def test_unhealthy_readiness_fails_closed_without_writing():
    state = OperationState("false")
    original_handler = state.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == HOSTNAME and request.url.path == "/health/ready":
            return httpx.Response(503, json={"status": "not_ready"})
        return original_handler(request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ResearchIntelligenceConfigurationError, match="control request failed"),
    ):
        set_research_intelligence_enabled(
            True,
            environ=environment(),
            client=client,
            token="fixed-worker-token",
            revision_lookup=state.revision_lookup,
            wait=lambda _seconds: None,
        )
    assert state.put_payloads == []


def test_unrelated_setting_drift_after_write_fails_closed():
    state = OperationState("false")
    original_handler = state.handler

    def handler(request: httpx.Request) -> httpx.Response:
        response = original_handler(request)
        if request.method == "PUT":
            state.settings["UNRELATED_SECRET"] = "unexpected-change"
        return response

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(
            ResearchIntelligenceConfigurationError,
            match="Unrelated production settings changed",
        ),
    ):
        set_research_intelligence_enabled(
            True,
            environ=environment(),
            client=client,
            token="fixed-worker-token",
            revision_lookup=state.revision_lookup,
            wait=lambda _seconds: None,
        )
