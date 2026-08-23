"""Tenant-scoped, source-first data assembly for researcher workspaces.

The models deliberately keep qualitative entry payloads flexible.  This module
turns those stored payloads into display data without inventing coding or
analysis, and keeps every caller responsible for supplying an already
authorised study scope.
"""

from __future__ import annotations

import json
from collections import Counter


def response_payload(value: str) -> dict:
    try:
        payload = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def response_body(value: str) -> str:
    payload = response_payload(value)
    text = payload.get("text") or payload.get("value") or payload.get("answer") or ""
    return text.strip() if isinstance(text, str) else ""


def response_codes(value: str) -> list[str]:
    payload = response_payload(value)
    raw = payload.get("researcher_codes") or payload.get("codes") or []
    if not isinstance(raw, list):
        return []
    codes: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            codes.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("label") or item.get("code")
            if isinstance(label, str) and label.strip():
                codes.append(label.strip())
    return codes


def response_context(value: str) -> dict[str, str]:
    payload = response_payload(value)
    fields = ("observed_at", "place", "trajectory_stage")
    return {
        field: payload[field].strip()
        for field in fields
        if isinstance(payload.get(field), str) and payload[field].strip()
    }


def code_counts(responses) -> Counter[str]:
    counts: Counter[str] = Counter()
    for response in responses:
        counts.update(response_codes(response.value_json))
    return counts
