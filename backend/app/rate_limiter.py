from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after: int


class RateLimiter:
    """In-memory fixed-window rate limiter with burst support."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        burst: int | None = None,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.burst = burst or limit
        self._time = time_func or time.monotonic
        self._requests: Dict[str, Deque[float]] = {}

    def configure(
        self,
        *,
        limit: int | None = None,
        burst: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        if limit is not None:
            self.limit = limit
        if burst is not None:
            self.burst = burst
        if window_seconds is not None:
            self.window_seconds = window_seconds

    def reset(self) -> None:
        self._requests.clear()

    def _prune(self, key: str, now: float) -> None:
        bucket = self._requests.setdefault(key, deque())
        window = self.window_seconds
        while bucket and now - bucket[0] >= window:
            bucket.popleft()

    def consume(self, key: str) -> RateLimitResult:
        now = self._time()
        bucket = self._requests.setdefault(key, deque())
        self._prune(key, now)

        if len(bucket) >= self.burst:
            retry_after = self._retry_after(bucket, now)
            return RateLimitResult(allowed=False, retry_after=retry_after)

        bucket.append(now)
        return RateLimitResult(allowed=True, retry_after=0)

    def _retry_after(self, bucket: Deque[float], now: float) -> int:
        if not bucket:
            return 0
        oldest = bucket[0]
        remaining = self.window_seconds - (now - oldest)
        if remaining <= 0:
            return 0
        return max(1, int(math.ceil(remaining)))


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after


__all__ = ["RateLimiter", "RateLimitResult", "RateLimitExceeded"]
