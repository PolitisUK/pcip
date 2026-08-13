"""Scope-safe, source-first evidence exploration helpers.

The explorer deliberately searches submitted source material rather than treating
AI output as evidence.  AI suggestions may help researchers filter material, but
their review status is always returned separately.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .research_intelligence import response_text


@dataclass(frozen=True)
class EvidenceItem:
    response_id: int
    participant_id: int
    participant_reference: str
    activity_id: int
    activity_title: str
    source_excerpt: str
    source_truncated: bool
    submitted_at: datetime | None
    updated_at: datetime
    suggested_codes: list[str]
    analysis_status: str | None


def _codes(value: str) -> list[str]:
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    codes = []
    for item in decoded:
        if isinstance(item, str) and item.strip():
            codes.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("label") or item.get("code")
            if isinstance(label, str) and label.strip():
                codes.append(label.strip())
    return codes


def _excerpt(value: str, maximum: int = 1200) -> tuple[str, bool]:
    """Return verbatim source text only; callers can safely label it a quote."""
    return value[:maximum], len(value) > maximum


def evidence_items(
    responses: Iterable,
    *,
    activities: dict[int, object],
    participants: dict[int, object],
    suggestions: Iterable,
) -> list[EvidenceItem]:
    """Build source-citable items using only already scope-filtered rows."""
    latest_suggestion: dict[int, object] = {}
    for suggestion in suggestions:
        latest_suggestion.setdefault(suggestion.source_response_id, suggestion)

    items = []
    for response in responses:
        try:
            source = response_text(response)
        except ValueError:
            continue
        participant = participants.get(response.participant_id)
        activity = activities.get(response.activity_id)
        if not participant or not activity:
            continue
        suggestion = latest_suggestion.get(response.id)
        excerpt, truncated = _excerpt(source)
        items.append(
            EvidenceItem(
                response_id=response.id,
                participant_id=response.participant_id,
                participant_reference=participant.reference,
                activity_id=response.activity_id,
                activity_title=activity.title,
                source_excerpt=excerpt,
                source_truncated=truncated,
                submitted_at=response.submitted_at,
                updated_at=response.updated_at,
                suggested_codes=(
                    _codes(suggestion.suggested_codes_json) if suggestion else []
                ),
                analysis_status=suggestion.status if suggestion else None,
            )
        )
    return items


def filter_evidence(
    items: Iterable[EvidenceItem],
    *,
    query: str = "",
    code: str = "",
    participant_id: int | None = None,
    analysis_status: str = "all",
) -> list[EvidenceItem]:
    """Apply transparent local filters without generating or altering evidence."""
    query_terms = [term for term in query.casefold().split() if term]
    wanted_code = code.strip().casefold()
    filtered = []
    for item in items:
        haystack = f"{item.source_excerpt} {item.activity_title}".casefold()
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        item_codes = {suggested.casefold() for suggested in item.suggested_codes}
        if wanted_code and wanted_code not in item_codes:
            continue
        if participant_id is not None and item.participant_id != participant_id:
            continue
        if analysis_status != "all" and item.analysis_status != analysis_status:
            continue
        filtered.append(item)
    return sorted(filtered, key=lambda item: item.updated_at, reverse=True)
