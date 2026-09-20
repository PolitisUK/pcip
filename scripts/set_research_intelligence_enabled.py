"""Toggle the single approved Research Intelligence production setting.

This module is an implementation detail of the protected production-operations
worker.  It accepts only a boolean target state and resolves the production App
Service from fixed worker environment variables.  It is deliberately not a
generic App Service configuration facility.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential

from scripts.get_alembic_revision import execute_get_alembic_revision

SETTING_NAME = "RESEARCH_INTELLIGENCE_ENABLED"
ARM_SCOPE = "https://management.azure.com/.default"
ARM_API_VERSION = "2024-04-01"
IMMUTABLE_IMAGE_PATTERN = re.compile(r"@(?P<digest>sha256:[0-9a-f]{64})\Z")
RELEASE_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
REVISION_PATTERN = re.compile(r"[0-9]{4}\Z")
SAFETY_SETTINGS = {
    "RUN_MIGRATIONS": "false",
    "SEED_DEMO_DATA": "false",
    "RUN_RIVERMERE_PRODUCTION_DEMO_SEED": "false",
}
OPTIONAL_SEEDING_SETTINGS = ("RUN_RIVERMERE_DEMO_SEED",)
PUBLIC_PATHS = ("/", "/privacy", "/terms")


class ResearchIntelligenceConfigurationError(RuntimeError):
    """Raised when the fixed operation cannot prove a safe result."""


@dataclass(frozen=True)
class ResearchIntelligenceConfigurationResult:
    prior_value: bool
    requested_value: bool
    effective_value: bool
    readiness_status: str
    release_sha: str
    image_digest: str
    alembic_revision: str

    def approved_result(self) -> dict[str, str | bool]:
        return asdict(self)


def _required_environment(environ: Mapping[str, str]) -> tuple[str, str, str]:
    subscription_id = environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    resource_group = environ.get("AZURE_RESOURCE_GROUP", "").strip()
    app_name = environ.get("PCIP_PRODUCTION_APP", "").strip()
    if not subscription_id or not resource_group or not app_name:
        raise ResearchIntelligenceConfigurationError("Fixed production target is unavailable.")
    return subscription_id, resource_group, app_name


def _response_json(response: httpx.Response) -> dict[str, Any]:
    if response.status_code < 200 or response.status_code >= 300:
        raise ResearchIntelligenceConfigurationError("Production control request failed.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ResearchIntelligenceConfigurationError("Production control response was invalid.") from exc
    if not isinstance(payload, dict):
        raise ResearchIntelligenceConfigurationError("Production control response was invalid.")
    return payload


def _arm_request(
    client: httpx.Client,
    token: str,
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _response_json(
        client.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30,
        )
    )


def _site_state(client: httpx.Client, token: str, site_url: str) -> tuple[str, str]:
    site = _arm_request(client, token, "GET", site_url)
    properties = site.get("properties")
    if not isinstance(properties, dict):
        raise ResearchIntelligenceConfigurationError("Production App Service metadata was invalid.")
    hostname = properties.get("defaultHostName")
    site_config = properties.get("siteConfig")
    image = site_config.get("linuxFxVersion") if isinstance(site_config, dict) else None
    match = IMMUTABLE_IMAGE_PATTERN.search(image) if isinstance(image, str) else None
    if not isinstance(hostname, str) or not hostname or match is None:
        raise ResearchIntelligenceConfigurationError("Production App Service metadata was invalid.")
    return hostname, match.group("digest")


def _settings(client: httpx.Client, token: str, settings_url: str) -> dict[str, str]:
    payload = _arm_request(
        client,
        token,
        "POST",
        f"{settings_url}/list?api-version={ARM_API_VERSION}",
    )
    properties = payload.get("properties")
    if not isinstance(properties, dict) or not all(
        isinstance(name, str) and isinstance(value, str)
        for name, value in properties.items()
    ):
        raise ResearchIntelligenceConfigurationError("Production settings response was invalid.")
    return dict(properties)


def _boolean_setting(settings: Mapping[str, str], name: str, *, default: bool = False) -> bool:
    value = settings.get(name)
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ResearchIntelligenceConfigurationError("Production boolean setting was invalid.")


def _validate_safety_settings(settings: Mapping[str, str]) -> None:
    for name, expected in SAFETY_SETTINGS.items():
        if settings.get(name, "").strip().lower() != expected:
            raise ResearchIntelligenceConfigurationError("Production safety setting was not preserved.")
    for name in OPTIONAL_SEEDING_SETTINGS:
        if name in settings and settings[name].strip().lower() != "false":
            raise ResearchIntelligenceConfigurationError("Production safety setting was not preserved.")


def _readiness(client: httpx.Client, hostname: str) -> tuple[str, str]:
    response = client.get(f"https://{hostname}/health/ready", timeout=30)
    payload = _response_json(response)
    status = payload.get("status")
    revision = payload.get("revision")
    if status != "ready" or not isinstance(revision, str) or RELEASE_PATTERN.fullmatch(revision) is None:
        raise ResearchIntelligenceConfigurationError("Production readiness was not healthy.")
    return status, revision


def _public_routes(client: httpx.Client, hostname: str) -> None:
    for path in PUBLIC_PATHS:
        response = client.get(f"https://{hostname}{path}", follow_redirects=True, timeout=30)
        if response.status_code != 200:
            raise ResearchIntelligenceConfigurationError("Production public route was not healthy.")


def _alembic_revision(revision_lookup: Callable[[], Any]) -> str:
    try:
        result = revision_lookup().approved_result()
    except Exception as exc:
        raise ResearchIntelligenceConfigurationError("Alembic revision could not be verified.") from exc
    revision = result.get("alembic_revision") if isinstance(result, dict) else None
    if not isinstance(revision, str) or REVISION_PATTERN.fullmatch(revision) is None:
        raise ResearchIntelligenceConfigurationError("Alembic revision could not be verified.")
    return revision


def set_research_intelligence_enabled(
    enabled: bool,
    *,
    environ: Mapping[str, str],
    client: httpx.Client,
    token: str,
    revision_lookup: Callable[[], Any] = execute_get_alembic_revision,
    wait: Callable[[float], None] = time.sleep,
) -> ResearchIntelligenceConfigurationResult:
    """Set only the fixed flag and fail closed on any release or safety drift."""
    if type(enabled) is not bool:
        raise ResearchIntelligenceConfigurationError("The requested value must be boolean.")
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
    prior_value = _boolean_setting(before, SETTING_NAME)

    if prior_value != enabled:
        updated = dict(before)
        updated[SETTING_NAME] = "true" if enabled else "false"
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
            raise ResearchIntelligenceConfigurationError("Production release changed during the operation.")
        if _boolean_setting(effective, SETTING_NAME) == enabled and current_status == "ready":
            readiness_status = current_status
            break
        wait(10)
    else:  # pragma: no cover - defensive; the bounded loop either breaks or raises.
        raise ResearchIntelligenceConfigurationError("Production configuration did not become ready.")

    if effective is None:
        raise ResearchIntelligenceConfigurationError("Production settings could not be verified.")
    _validate_safety_settings(effective)
    if {key: value for key, value in effective.items() if key != SETTING_NAME} != {
        key: value for key, value in before.items() if key != SETTING_NAME
    }:
        raise ResearchIntelligenceConfigurationError("Unrelated production settings changed.")
    after_hostname, after_digest = _site_state(client, token, site_url)
    if after_hostname != hostname or after_digest != image_digest:
        raise ResearchIntelligenceConfigurationError("Production image changed during the operation.")
    after_revision = _alembic_revision(revision_lookup)
    if after_revision != before_revision:
        raise ResearchIntelligenceConfigurationError("Alembic revision changed during the operation.")
    _public_routes(client, hostname)
    return ResearchIntelligenceConfigurationResult(
        prior_value=prior_value,
        requested_value=enabled,
        effective_value=_boolean_setting(effective, SETTING_NAME),
        readiness_status=readiness_status,
        release_sha=release_sha,
        image_digest=image_digest,
        alembic_revision=after_revision,
    )


def execute_set_research_intelligence_enabled(
    enabled: bool,
    *,
    environ: Mapping[str, str] | None = None,
    credential_factory: Callable[..., Any] = DefaultAzureCredential,
    client_factory: Callable[[], httpx.Client] = httpx.Client,
) -> ResearchIntelligenceConfigurationResult:
    """Resolve fixed production configuration and execute the approved toggle."""
    values = os.environ if environ is None else environ
    credential = credential_factory(exclude_interactive_browser_credential=True)
    token = credential.get_token(ARM_SCOPE).token
    with client_factory() as client:
        return set_research_intelligence_enabled(
            enabled,
            environ=values,
            client=client,
            token=token,
        )
