"""Token-bucket rate limiter - the book's exact rule (ch. 9.3.2).

tokens <- min(C, tokens + r * dt);  allow  <=>  tokens >= 1.
Rate-limit tokens, NOT LLM tokens (the book's three-token disambiguation).
"""

from __future__ import annotations

import time
from collections.abc import Callable


class TokenBucket:
    def __init__(self, *, capacity: float, refill_rate: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self._clock = clock
        self.tokens = capacity  # start full
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        self.tokens = min(self.capacity, self.tokens + (now - self._last) * self.refill_rate)
        self._last = now

    def allow(self, cost: float = 1.0) -> bool:
        """Spend a token if available, else block the caller (who must back off)."""
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
