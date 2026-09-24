"""Configure the single fixed production Azure OpenAI provider.

This is deliberately not a generic App Service configuration operation.  The
target application and all four provider values are compiled into the reviewed
worker revision; callers supply only the operation name and correlation ID.
The provider-backed feature gates must remain disabled throughout.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential

from scripts.get_alembic_revision import execute_get_alembic_revision
from scripts.set_research_intelligence_enabled import (
    AI_CODING_SETTING_NAME,
    ARM_API_VERSION,
    ARM_SCOPE,
    ResearchIntelligenceConfigurationError,
    _alembic_revision,
    _arm_request,
    _boolean_setting,
    _public_routes,
    _readiness,
    _required_environment,
    _settings,
    _site_state,
    _validate_safety_settings,
)

PROVIDER_SETTINGS = {
    "AZURE_OPENAI_ENDPOINT": "https://pcip-production-research-ai-rx6kbu.openai.azure.com/",
    "AZURE_OPENAI_ALLOWED_HOSTS": "pcip-production-research-ai-rx6kbu.openai.azure.com",
    "AZURE_OPENAI_DEPLOYMENT": "research-assistant-gpt41mini",
    "AZURE_OPENAI_AUTHENTICATION": "managed_identity",
}
SEMANTIC_SEARCH_SETTING_NAME = "RESEARCH_INTELLIGENCE_SEMANTIC_SEARCH_ENABLED"


@dataclass(frozen=True)
class ResearchAiProviderConfigurationResult:
    prior_configured: bool
    effective_configured: bool
    ai_coding_enabled: bool
    semantic_search_enabled: bool
    readiness_status: str
    release_sha: str
    image_digest: str
    alembic_revision: str

    def approved_result(self) -> dict[str, str | bool]:
        return asdict(self)


def _provider_configured(settings: Mapping[str, str]) -> bool:
    return all(settings.get(name) == value for name, value in PROVIDER_SETTINGS.items())


def _validate_provider_gates(settings: Mapping[str, str]) -> None:
    if _boolean_setting(settings, AI_CODING_SETTING_NAME) or _boolean_setting(
        settings, SEMANTIC_SEARCH_SETTING_NAME
    ):
        raise ResearchIntelligenceConfigurationError(
            "Production AI gate was not disabled."
        )


def configure_research_ai_provider(
    *,
    environ: Mapping[str, str],
    client: httpx.Client,
    token: str,
    revision_lookup: Callable[[], Any] = execute_get_alembic_revision,
    wait: Callable[[float], None],
) -> ResearchAiProviderConfigurationResult:
    """Set only the reviewed provider values and prove all safety invariants."""
    subscription_id, resource_group, app_name = _required_environment(environ)
    base_url = (
        "https://management.azure.com/subscriptions/"
        f"{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Web/sites/{app_name}"
    )
    site_url = f"{base_url}?api-version={ARM_API_VERSION}"
    settings_url = f"{base_url}/config/appsettings"
    hostname, image_digest = _site_state(client, token, site_url)
    readiness_status, release_sha = _readiness(client, hostname)
    before_revision = _alembic_revision(revision_lookup)
    before = _settings(client, token, settings_url)
    _validate_safety_settings(before)
    _validate_provider_gates(before)
    prior_configured = _provider_configured(before)

    if not prior_configured:
        updated = dict(before)
        updated.update(PROVIDER_SETTINGS)
        _arm_request(
            client,
            token,
            "PUT",
            f"{settings_url}?api-version={ARM_API_VERSION}",
            payload={"properties": updated},
        )

    effective: dict[str, str] | None = None
    for attempt in range(24):
        try:
            effective = _settings(client, token, settings_url)
            current_status, current_sha = _readiness(client, hostname)
        except (httpx.HTTPError, ResearchIntelligenceConfigurationError):
            if attempt == 23:
                raise
            wait(10)
            continue
        if current_sha != release_sha:
            raise ResearchIntelligenceConfigurationError(
                "Production release changed during the operation."
            )
        if _provider_configured(effective) and current_status == "ready":
            readiness_status = current_status
            break
        wait(10)
    else:  # pragma: no cover
        raise ResearchIntelligenceConfigurationError(
            "Production configuration did not become ready."
        )

    if effective is None:
        raise ResearchIntelligenceConfigurationError(
            "Production settings could not be verified."
        )
    _validate_safety_settings(effective)
    _validate_provider_gates(effective)
    provider_names = set(PROVIDER_SETTINGS)
    if {k: v for k, v in effective.items() if k not in provider_names} != {
        k: v for k, v in before.items() if k not in provider_names
    }:
        raise ResearchIntelligenceConfigurationError(
            "Unrelated production settings changed."
        )
    after_hostname, after_digest = _site_state(client, token, site_url)
    if after_hostname != hostname or after_digest != image_digest:
        raise ResearchIntelligenceConfigurationError(
            "Production image changed during the operation."
        )
    after_revision = _alembic_revision(revision_lookup)
    if after_revision != before_revision:
        raise ResearchIntelligenceConfigurationError(
            "Alembic revision changed during the operation."
        )
    _public_routes(client, hostname)
    return ResearchAiProviderConfigurationResult(
        prior_configured=prior_configured,
        effective_configured=_provider_configured(effective),
        ai_coding_enabled=False,
        semantic_search_enabled=False,
        readiness_status=readiness_status,
        release_sha=release_sha,
        image_digest=image_digest,
        alembic_revision=after_revision,
    )


def execute_configure_research_ai_provider(
    *,
    environ: Mapping[str, str] | None = None,
    credential_factory: Callable[..., Any] = DefaultAzureCredential,
    client_factory: Callable[[], httpx.Client] = httpx.Client,
) -> ResearchAiProviderConfigurationResult:
    values = os.environ if environ is None else environ
    credential = credential_factory(exclude_interactive_browser_credential=True)
    token = credential.get_token(ARM_SCOPE).token
    with client_factory() as client:
        return configure_research_ai_provider(
            environ=values,
            client=client,
            token=token,
            wait=time.sleep,
        )
