"""Validate the approved wall-clock window for a production release."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


LOCAL_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"


class ReleaseWindowError(ValueError):
    """Raised when an approved production release window is unusable."""


@dataclass(frozen=True)
class ReleaseWindow:
    start: datetime
    end: datetime
    timezone_name: str


def _parse_local_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.strptime(value, LOCAL_TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise ReleaseWindowError(
            f"{field_name} must use YYYY-MM-DDTHH:MM:SS local time."
        ) from exc
    if parsed.strftime(LOCAL_TIMESTAMP_FORMAT) != value:
        raise ReleaseWindowError(
            f"{field_name} must use YYYY-MM-DDTHH:MM:SS local time."
        )
    return parsed


def _resolve_local_time(
    value: datetime, *, timezone: ZoneInfo, field_name: str
) -> datetime:
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        local = value.replace(tzinfo=timezone, fold=fold)
        utc_value = local.astimezone(UTC)
        round_trip = utc_value.astimezone(timezone)
        if round_trip.replace(tzinfo=None) == value and round_trip.fold == fold:
            candidates[utc_value] = local

    if len(candidates) != 1:
        raise ReleaseWindowError(
            f"{field_name} is ambiguous or does not exist in the approved timezone."
        )
    return next(iter(candidates.values()))


def parse_release_window(start: str, end: str, timezone_name: str) -> ReleaseWindow:
    if not timezone_name or timezone_name.strip() != timezone_name:
        raise ReleaseWindowError(
            "release_window_timezone must be an exact supported IANA timezone name."
        )
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ReleaseWindowError(
            "release_window_timezone must be an exact supported IANA timezone name."
        ) from exc

    start_local = _resolve_local_time(
        _parse_local_timestamp(start, field_name="release_window_start"),
        timezone=timezone,
        field_name="release_window_start",
    )
    end_local = _resolve_local_time(
        _parse_local_timestamp(end, field_name="release_window_end"),
        timezone=timezone,
        field_name="release_window_end",
    )
    if end_local.astimezone(UTC) <= start_local.astimezone(UTC):
        raise ReleaseWindowError(
            "release_window_end must be later than release_window_start."
        )
    return ReleaseWindow(
        start=start_local,
        end=end_local,
        timezone_name=timezone_name,
    )


def enforce_release_window(
    start: str,
    end: str,
    timezone_name: str,
    *,
    now: datetime | None = None,
) -> ReleaseWindow:
    window = parse_release_window(start, end, timezone_name)
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ReleaseWindowError("Current execution time must be timezone-aware.")
    current_utc = current.astimezone(UTC)
    if current_utc < window.start.astimezone(UTC):
        raise ReleaseWindowError(
            "Production release window has not started. Wait for the approved start time."
        )
    if current_utc >= window.end.astimezone(UTC):
        raise ReleaseWindowError(
            "Production release window has expired. Obtain a new approved release window."
        )
    return window


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail closed unless an approved production release window is valid."
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate window metadata without requiring the window to be active.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.validate_only:
            parse_release_window(args.start, args.end, args.timezone)
            print("Production release window metadata is valid.")
        else:
            enforce_release_window(args.start, args.end, args.timezone)
            print("Production release window is active.")
    except ReleaseWindowError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
