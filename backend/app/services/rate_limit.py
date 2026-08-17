"""In-memory per-user rate limits and in-flight process locks.

Fine for a single Render web process. Not shared across replicas.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

PROCESS_LIMIT = 6
PROCESS_WINDOW_S = 15 * 60
UPLOAD_LIMIT = 12
UPLOAD_WINDOW_S = 15 * 60


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        ts = time.monotonic() if now is None else now
        bucket = self._hits[key]
        cutoff = ts - self.window_s
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry = int(max(1, self.window_s - (ts - bucket[0])))
            return False, retry
        bucket.append(ts)
        return True, 0


class InFlightSet:
    def __init__(self) -> None:
        self._ids: set[str] = set()

    def acquire(self, clip_id: str) -> bool:
        if clip_id in self._ids:
            return False
        self._ids.add(clip_id)
        return True

    def release(self, clip_id: str) -> None:
        self._ids.discard(clip_id)

    def contains(self, clip_id: str) -> bool:
        return clip_id in self._ids


process_limiter = SlidingWindowLimiter(PROCESS_LIMIT, PROCESS_WINDOW_S)
upload_limiter = SlidingWindowLimiter(UPLOAD_LIMIT, UPLOAD_WINDOW_S)
inflight_clips = InFlightSet()
