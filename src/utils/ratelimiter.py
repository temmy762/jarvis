"""Simple per-user rate limiting utilities for Jarvis.

This module currently implements an in-memory fixed-window rate limiter.
In production, you should replace the storage backend with Redis.
"""

from __future__ import annotations

import time
from typing import Dict
from typing import Tuple

REQUEST_LIMIT = 20       # max requests per window
WINDOW_SECONDS = 60      # length of window in seconds

# In-memory store: user_id -> (window_start_timestamp, count)
_rate_state: Dict[str, Tuple[float, int]] = {}


async def check_rate_limit(user_id: str) -> bool:
    """Return True if the user is within the limit, False if rate-limited.

    Fixed-window algorithm using an in-memory dictionary. This is sufficient
    for a single-process deployment. For production, replace with a Redis-
    backed implementation using INCR + TTL.
    """

    now = time.time()
    window_start, count = _rate_state.get(user_id, (now, 0))

    # If the previous window has expired, reset it.
    if now - window_start >= WINDOW_SECONDS:
        window_start = now
        count = 0

    if count >= REQUEST_LIMIT:
        # Already at or above the limit for this window.
        _rate_state[user_id] = (window_start, count)
        return False

    # Increment and store.
    count += 1
    _rate_state[user_id] = (window_start, count)
    return True
