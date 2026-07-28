"""Deadline Tracker (rule #6): no request ever waits unbounded.

A transport call gets a per-request timeout, bounded retries with backoff,
and then a DeadlineExpiredError that the caller turns into a clean technical
loss - a missed deadline is a failure, not patience (book ch. 8.4).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class DeadlineExpiredError(RuntimeError):
    pass


class DeadlineTracker:
    def __init__(self, *, timeout_sec: float, max_retries: int, backoff_sec: float,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_sec = backoff_sec
        self._sleep = sleep
        self.last_error: Exception | None = None

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run ``fn`` (which must honor ``timeout_sec`` itself) with bounded retries."""
        for attempt in range(self.max_retries + 1):
            try:
                return fn(*args, timeout=self.timeout_sec, **kwargs)
            except Exception as exc:  # noqa: BLE001 - transport errors are heterogeneous
                self.last_error = exc
                if attempt < self.max_retries:
                    self._sleep(self.backoff_sec)
        raise DeadlineExpiredError(
            f"no response after {self.max_retries + 1} attempts: {self.last_error}"
        ) from self.last_error
