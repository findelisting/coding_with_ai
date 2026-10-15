"""In-memory per-user rate limit (v1). Single process only; move to Redis when scaling out."""

import math
import time
from collections import defaultdict, deque

from app.errors import ApiError


class RateLimiter:
    def __init__(self, limit: int = 60, window_s: float = 60.0):
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = math.ceil(self.window_s - (now - hits[0]))
            raise ApiError(429, "rate_limited", "Too many requests",
                           headers={"Retry-After": str(max(retry_after, 1))})
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


location_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return location_rate_limiter
