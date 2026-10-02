"""Per-client limit on new victim sessions (PC-13 A, EXT-130 hosted tester build).

Standard library only, in memory, one process. Off unless
SESSION_RATE_LIMIT_PER_HOUR is above zero, so the local and demo builds keep
the frozen PC-09 behaviour exactly. The key is the client address uvicorn
reports (the forwarded address when it runs with --proxy-headers); it is
never logged or returned.
"""

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict

WINDOW_SECONDS = 3600.0


class SessionRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._seen: Dict[str, Deque[float]] = {}

    def allow(self, client: str, limit_per_hour: int) -> bool:
        """Record one attempt; False once `client` exceeds the limit in a rolling hour."""
        if limit_per_hour <= 0:
            return True
        now = self._clock()
        with self._lock:
            stamps = self._seen.setdefault(client, deque())
            while stamps and now - stamps[0] >= WINDOW_SECONDS:
                stamps.popleft()
            if len(stamps) >= limit_per_hour:
                return False
            stamps.append(now)
            # Forget clients with nothing left in the window, so memory stays bounded.
            for key in [k for k, v in self._seen.items() if v and now - v[-1] >= WINDOW_SECONDS]:
                del self._seen[key]
            return True

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()


session_limiter = SessionRateLimiter()
