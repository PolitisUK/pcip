from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from scripts.configure_research_ai_provider import (
    PROVIDER_SETTINGS,
    configure_research_ai_provider,
)
from scripts.set_research_intelligence_enabled import (
    ResearchIntelligenceConfigurationError,
)

RELEASE_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
HOSTNAME = "production.example.test"


class State:
    def __init__(self, *, configured: bool = False):
        self.settings = {
            "RUN_MIGRATIONS": "false",
            "SEED_DEMO_DATA": "false",
            "RUN_RIVERMERE_PRODUCTION_DEMO_SEED": "false",
            "RESEARCH_INTELLIGENCE_AI_CODING_ENABLED": "false",
            "RESEARCH_INTELLIGENCE_SEMANTIC_SEARCH_ENABLED": "false",
            "UNRELATED_SECRET": "preserved",
        }
        if configured:
            self.settings.update(PROVIDER_SETTINGS)
        self.put_payloads: list[dict] = []
        self.release_shas = [RELEASE_SHA]
        self.image_digests = [IMAGE_DIGEST]
        self.revisions = ["0037"]
        self.public_paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "management.azure.com":
            if request.method == "GET" and "/config/" not in request.url.path:
                digest = (
                    self.image_digests.pop(0)
                    if len(self.image_digests) > 1
                    else self.image_digests[0]
                )
                return httpx.Response(
                    200,
                    json={
                        "properties": {
                            "defaultHostName": HOSTNAME,
                            "siteConfig": {
                                "linuxFxVersion": f"DOCKER|registry/pcip@{digest}"
                            },
                        }
                    },
                )
            if request.method == "POST" and request.url.path.endswith(
                "/config/appsettings/list"
            ):
                return httpx.Response(200, json={"properties": dict(self.settings)})
            if request.method == "PUT" and request.url.path.endswith(
                "/config/appsettings"
            ):
                payload = json.loads(request.content)
                self.put_payloads.append(payload)
                self.settings = dict(payload["properties"])
                return httpx.Response(200, json={"properties": dict(self.settings)})
        if request.url.host == HOSTNAME and request.url.path == "/health/ready":
            release = (
                self.release_shas.pop(0)
                if len(self.release_shas) > 1
                else self.release_shas[0]
            )
            return httpx.Response(200, json={"status": "ready", "revision": release})
        if request.url.host == HOSTNAME and request.url.path in {
            "/",
            "/privacy",
            "/terms",
        }:
            self.public_paths.append(request.url.path)
            return httpx.Response(200, text="ok")
        return httpx.Response(404)

    def revision_lookup(self):
        revision = (
            self.revisions.pop(0) if len(self.revisions) > 1 else self.revisions[0]
        )
        return SimpleNamespace(approved_result=lambda: {"alembic_revision": revision})


def run(state: State):
    with httpx.Client(transport=httpx.MockTransport(state.handler)) as client:
        return configure_research_ai_provider(
            environ={
                "AZURE_SUBSCRIPTION_ID": "11111111-1111-1111-1111-111111111111",
                "AZURE_RESOURCE_GROUP": "rg-pcip-prod",
                "PCIP_PRODUCTION_APP": "citizencentric-pcip-prod",
            },
            client=client,
            token="fixed-worker-token",
            revision_lookup=state.revision_lookup,
            wait=lambda _seconds: None,
        )


def test_fixed_provider_operation_sets_only_exact_allowlisted_values():
    state = State()
    before = dict(state.settings)
    result = run(state)
    assert len(state.put_payloads) == 1
    written = state.put_payloads[0]["properties"]
    assert {name: written[name] for name in PROVIDER_SETTINGS} == PROVIDER_SETTINGS
    assert {k: v for k, v in written.items() if k not in PROVIDER_SETTINGS} == before
    assert result.prior_configured is False
    assert result.effective_configured is True
    assert result.ai_coding_enabled is False
    assert result.semantic_search_enabled is False
    assert state.public_paths == ["/", "/privacy", "/terms"]


def test_fixed_provider_operation_is_idempotent():
    state = State(configured=True)
    result = run(state)
    assert state.put_payloads == []
    assert result.prior_configured is True
    assert result.effective_configured is True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RESEARCH_INTELLIGENCE_AI_CODING_ENABLED", "true"),
        ("RESEARCH_INTELLIGENCE_SEMANTIC_SEARCH_ENABLED", "true"),
        ("RUN_MIGRATIONS", "true"),
        ("SEED_DEMO_DATA", "true"),
        ("RUN_RIVERMERE_PRODUCTION_DEMO_SEED", "true"),
    ],
)
def test_fixed_provider_operation_refuses_unsafe_flags_before_write(name, value):
    state = State()
    state.settings[name] = value
    with pytest.raises(ResearchIntelligenceConfigurationError):
        run(state)
    assert state.put_payloads == []


def test_fixed_provider_operation_fails_on_unrelated_setting_drift():
    state = State()
    original = state.handler

    def handler(request: httpx.Request) -> httpx.Response:
        response = original(request)
        if request.method == "PUT":
            state.settings["UNRELATED_SECRET"] = "changed"
        return response

    state.handler = handler  # type: ignore[method-assign]
    with pytest.raises(ResearchIntelligenceConfigurationError, match="Unrelated"):
        run(state)


def test_fixed_provider_operation_fails_on_release_image_or_schema_drift():
    for attribute, values, match in (
        ("release_shas", [RELEASE_SHA, "c" * 40], "release changed"),
        ("image_digests", [IMAGE_DIGEST, "sha256:" + "c" * 64], "image changed"),
        ("revisions", ["0037", "0038"], "Alembic revision changed"),
    ):
        state = State()
        setattr(state, attribute, values)
        with pytest.raises(ResearchIntelligenceConfigurationError, match=match):
            run(state)
