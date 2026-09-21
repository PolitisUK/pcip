from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.validate_release_window import (
    ReleaseWindowError,
    enforce_release_window,
    parse_release_window,
)


START = "2026-09-21T20:10:00"
END = "2026-09-21T22:30:00"
ZONE = "Europe/London"


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def test_current_time_inside_window_is_accepted():
    enforce_release_window(START, END, ZONE, now=utc("2026-09-21T20:00:00"))


def test_current_time_before_window_is_rejected():
    with pytest.raises(ReleaseWindowError, match="has not started"):
        enforce_release_window(START, END, ZONE, now=utc("2026-09-21T19:09:59"))


def test_current_time_after_window_is_rejected():
    with pytest.raises(ReleaseWindowError, match="has expired"):
        enforce_release_window(START, END, ZONE, now=utc("2026-09-21T21:30:01"))


def test_start_is_inclusive():
    enforce_release_window(START, END, ZONE, now=utc("2026-09-21T19:10:00"))


def test_end_is_exclusive():
    with pytest.raises(ReleaseWindowError, match="has expired"):
        enforce_release_window(START, END, ZONE, now=utc("2026-09-21T21:30:00"))


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("21 September 2026 20:10", END, "release_window_start"),
        (START, "tomorrow evening", "release_window_end"),
        (END, START, "must be later"),
        (START, START, "must be later"),
    ],
)
def test_invalid_window_values_are_rejected(start: str, end: str, message: str):
    with pytest.raises(ReleaseWindowError, match=message):
        parse_release_window(start, end, ZONE)


def test_invalid_or_ambiguous_timezone_is_rejected():
    with pytest.raises(ReleaseWindowError, match="IANA timezone"):
        parse_release_window(START, END, "BST")


def test_utc_to_bst_conversion_uses_the_approved_timezone():
    enforce_release_window(
        "2026-07-01T20:00:00",
        "2026-07-01T21:00:00",
        ZONE,
        now=utc("2026-07-01T19:30:00"),
    )


def test_window_can_roll_over_midnight():
    enforce_release_window(
        "2026-09-21T23:30:00",
        "2026-09-22T00:30:00",
        ZONE,
        now=utc("2026-09-21T23:00:00"),
    )


def test_stale_prior_day_approval_is_rejected():
    with pytest.raises(ReleaseWindowError, match="has expired"):
        enforce_release_window(
            "2026-09-20T20:10:00",
            "2026-09-20T22:30:00",
            ZONE,
            now=utc("2026-09-21T09:02:00"),
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-03-29T01:30:00", "2026-03-29T03:00:00"),
        ("2026-10-25T01:30:00", "2026-10-25T03:00:00"),
    ],
)
def test_nonexistent_or_ambiguous_dst_times_fail_closed(start: str, end: str):
    with pytest.raises(ReleaseWindowError, match="ambiguous or does not exist"):
        parse_release_window(start, end, ZONE)


def test_workflow_checks_window_after_approval_and_at_mutation_boundaries():
    workflow = Path(".github/workflows/promote-release.yml").read_text()

    assert "release_window_start:" in workflow
    assert "release_window_end:" in workflow
    assert "release_window_timezone:" in workflow
    assert "--validate-only" in workflow
    assert "environment: production" in workflow
    assert "Enforce approved production release window" in workflow
    assert workflow.count("python scripts/validate_release_window.py") >= 5
    first_enforcement = workflow.index("Enforce approved production release window")
    first_mutation = workflow.index("Enforce the no-migration production steady state")
    assert first_enforcement < first_mutation
    promotion = workflow.partition(
        "Promote the already-staged immutable artifact and run the one approved migration"
    )[2].partition("Verify the restarted production candidate")[0]
    assert promotion.count("python scripts/validate_release_window.py") == 2
    assert promotion.index("python scripts/validate_release_window.py") < promotion.index(
        "az acr import"
    )
    second_check = promotion.rindex("python scripts/validate_release_window.py")
    assert promotion.index("az acr import") < second_check
    assert second_check < promotion.index("RUN_MIGRATIONS=true")
    cleanup = workflow.partition(
        "Fail safe to the no-migration production steady state"
    )[2].partition("Verify final production steady state")[0]
    assert "validate_release_window.py" not in cleanup
