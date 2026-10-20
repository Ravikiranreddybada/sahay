"""Circuit breaker. Closed -> (N consecutive failures) -> Open -> (reset timeout) -> Half-open.

At 1 lakh users a slow provider is worse than a down one: requests pile up, the worker
pool saturates and *every* intent fails, not just the ones that need the big model.
The breaker turns a slow failure into a fast one so the router can fall back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    reset_timeout_s: float = 30.0
    _failures: int = 0
    _opened_at: float | None = None
    _half_open_probe: bool = field(default=False)

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self.reset_timeout_s:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        st = self.state
        if st == "closed":
            return True
        if st == "half_open" and not self._half_open_probe:
            self._half_open_probe = True  # let exactly one probe through
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._half_open_probe = False

    def record_failure(self) -> None:
        self._failures += 1
        self._half_open_probe = False
        if self._failures >= self.failure_threshold or self._opened_at is not None:
            self._opened_at = time.monotonic()
