"""Versioned, controlled methodology grounding for researcher-only AI support.

This module deliberately performs deterministic record retrieval.  It neither
trains a model nor indexes participant material, and it never selects a method
on behalf of a researcher.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


LIBRARY_PATH = Path(__file__).with_name("methodology_library") / "library_v1.json"
SOURCE_REGISTER_PATH = Path(__file__).with_name("methodology_library") / "source_register_v1.json"
PUBLISHED_STATE = "PUBLISHED"
LIBRARY_UPDATE_STATES = ("NEW", "REVIEWED", "TRIANGULATED", "APPROVED", "PUBLISHED")


class MethodologyGateViolation(ValueError):
    """Raised when an AI operation is not coherent with an approved study method."""


@dataclass(frozen=True)
class MethodologyGrounding:
    methodology_id: str
    methodology_name: str
    variant: str
    library_version: str
    rule_references: tuple[str, ...]
    warnings: tuple[str, ...]
    allowed_tasks: tuple[str, ...]


@lru_cache(maxsize=1)
def methodology_library() -> dict:
    payload = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    if payload.get("publication_state") != PUBLISHED_STATE:
        raise RuntimeError("Only a published methodology library can ground live research work.")
    if tuple(payload.get("update_workflow", ())) != LIBRARY_UPDATE_STATES:
        raise RuntimeError("The methodology library has an invalid controlled update workflow.")
    return payload


def library_records() -> tuple[dict, ...]:
    return tuple(methodology_library()["records"])


def get_methodology(methodology_id: str) -> dict:
    for record in library_records():
        if record["methodology_id"] == methodology_id:
            return record
    raise MethodologyGateViolation("Select an approved primary methodology.")


def methodology_options() -> tuple[dict, ...]:
    return tuple(
        {"id": row["methodology_id"], "name": row["name"], "variants": tuple(row["variants"])}
        for row in library_records()
    )


@lru_cache(maxsize=1)
def _source_register() -> dict[str, dict]:
    payload = json.loads(SOURCE_REGISTER_PATH.read_text(encoding="utf-8"))
    rows = [*payload.get("core_sources", []), *payload.get("external_sources", [])]
    return {str(item["id"]): item for item in rows if item.get("id")}


def source_metadata(source_ids: tuple[str, ...] | list[str]) -> tuple[dict, ...]:
    """Return bibliographic metadata only; never source text or internal paths."""
    register = _source_register()
    results = []
    for source_id in source_ids:
        row = register.get(source_id)
        if row is None:
            continue
        results.append({
            "id": source_id,
            "authors": row.get("authors", ""),
            "year": row.get("year", ""),
            "title": row.get("title", ""),
            "identifier": row.get("doi") or row.get("identifier", ""),
        })
    return tuple(results)


def _as_json_list(value: str | None) -> list[str]:
    try:
        result = json.loads(value or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in result if isinstance(item, str)]


def study_grounding(configuration, task: str) -> MethodologyGrounding:
    if configuration is None or not configuration.researcher_confirmed_at:
        raise MethodologyGateViolation("A researcher must confirm the study methodology before AI support is used.")
    if not configuration.ai_enabled:
        raise MethodologyGateViolation("AI support is not enabled for this study.")
    record = get_methodology(configuration.primary_methodology_id)
    variant = (configuration.methodology_variant or "").strip()
    if variant and variant not in record["variants"]:
        raise MethodologyGateViolation("The selected methodology variant is not approved for this methodology.")
    allowed_by_study = set(_as_json_list(configuration.allowed_ai_tasks_json))
    allowed_by_method = set(record["allowed_ai_tasks"])
    if task not in allowed_by_study or task not in allowed_by_method:
        raise MethodologyGateViolation("This AI task is not approved for the selected methodology and study protocol.")
    warnings = [item["warning"] for item in methodology_library()["disagreements"]]
    return MethodologyGrounding(
        methodology_id=record["methodology_id"],
        methodology_name=record["name"],
        variant=variant,
        library_version=configuration.library_version,
        rule_references=tuple(record["provenance"]),
        warnings=tuple(warnings),
        allowed_tasks=tuple(sorted(allowed_by_study & allowed_by_method)),
    )


def validate_configuration(
    *, primary_methodology_id: str, methodology_variant: str, secondary_methodologies: list[str],
    research_questions: str, protocol_reference: str, protocol_version: str,
    sampling_approach: str, data_collection_plan: str, ai_enabled: bool,
    allowed_ai_tasks: list[str], researcher_confirmation: bool,
) -> list[str]:
    record = get_methodology(primary_methodology_id)
    issues: list[str] = []
    if methodology_variant and methodology_variant not in record["variants"]:
        issues.append("Choose a variant listed for the selected methodology.")
    if not all(value.strip() for value in (research_questions, protocol_reference, protocol_version, sampling_approach, data_collection_plan)):
        issues.append("Research questions, protocol reference/version, sampling and collection plan are required.")
    secondary = set(secondary_methodologies)
    if primary_methodology_id in secondary:
        issues.append("A primary methodology cannot also be listed as a secondary method.")
    known = {row["methodology_id"] for row in library_records()}
    if not secondary.issubset(known):
        issues.append("Select secondary methods from the approved methodology library.")
    allowed = set(allowed_ai_tasks)
    method_allowed = set(record["allowed_ai_tasks"])
    if ai_enabled and not allowed:
        issues.append("Select at least one permitted AI support task or keep AI support disabled.")
    unsupported = allowed - method_allowed
    if unsupported:
        issues.append("METHODOLOGICAL REVIEW REQUIRED: the requested AI task conflicts with the selected methodology.")
    if primary_methodology_id == "M08" and {"coding_reliability", "intercoder_agreement"} & allowed:
        issues.append("METHODOLOGICAL REVIEW REQUIRED: reflexive thematic analysis does not use reliability metrics as its quality logic.")
    if primary_methodology_id == "M13" and allowed - {"retrieval"}:
        issues.append("METHODOLOGICAL REVIEW REQUIRED: conversation analysis requires detailed human-verified sequential evidence.")
    if primary_methodology_id == "M15" and "frequency_claim" in allowed:
        issues.append("METHODOLOGICAL REVIEW REQUIRED: IPA/phenomenological inquiry does not use frequency as its warrant.")
    if primary_methodology_id == "M20" and {"sampling_decision", "consent_decision", "governance_decision"} & allowed:
        issues.append("METHODOLOGICAL REVIEW REQUIRED: community decision rights cannot be delegated to AI.")
    if not researcher_confirmation:
        issues.append("A named researcher must confirm this methodology configuration.")
    return issues
