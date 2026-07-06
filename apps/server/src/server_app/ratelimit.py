"""Per-IP sliding-window rate limiter for the auth endpoints.

In-process on purpose: at ~10 users with 1–2 API replicas this is adequate
and dependency-free. If the API is ever scaled wider, move the counters to
Redis (same interface, INCR + EXPIRE) — noted in the deployment runbook.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Record an attempt. Returns None when allowed, otherwise the
        seconds until the caller may retry."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                return self.window_seconds - (now - hits[0])
            hits.append(now)
            return None
