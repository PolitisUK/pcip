from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field


@dataclass
class SimpleRateLimiter:
    _buckets: dict[str, deque[datetime]] = field(default_factory=dict)

    def _prune(self, key: str, window_seconds: int, now: datetime | None = None) -> None:
        bucket = self._buckets.get(key)
        if not bucket:
            return
        if now is None:
            now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if not bucket:
            self._buckets.pop(key, None)

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = datetime.now(timezone.utc)
        self._prune(key, window_seconds, now)
        bucket = self._buckets.setdefault(key, deque())
        if len(bucket) < limit:
            bucket.append(now)
            return None
        oldest = bucket[0]
        retry_after = max(1, int((oldest + timedelta(seconds=window_seconds) - now).total_seconds()))
        return retry_after

    def reset(self) -> None:
        self._buckets.clear()


class RedisRateLimiter(SimpleRateLimiter):
    pass


def build_rate_limiter(redis_url: str | None, redis_prefix: str | None):
    if not redis_url:
        return SimpleRateLimiter()
    return RedisRateLimiter()
