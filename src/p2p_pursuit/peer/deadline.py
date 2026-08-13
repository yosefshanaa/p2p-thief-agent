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
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 on_attempt: Callable[[], None] | None = None) -> None:
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_sec = backoff_sec
        self._sleep = sleep
        self._clock = clock
        self._on_attempt = on_attempt
        self.last_error: Exception | None = None

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run ``fn`` (which must honor ``timeout_sec`` itself) with bounded retries.

        ``on_attempt`` fires before every attempt so a caller can beat its
        watchdog: the full retry budget outlasts the watchdog threshold, and
        a peer waiting patiently on a slow-but-alive link must not be
        mistaken for a frozen loop and shut down.
        """
        for attempt in range(self.max_retries + 1):
            if self._on_attempt is not None:
                self._on_attempt()
            try:
                return fn(*args, timeout=self.timeout_sec, **kwargs)
            except Exception as exc:  # noqa: BLE001 - transport errors are heterogeneous
                self.last_error = exc
                if attempt < self.max_retries:
                    self._sleep(self.backoff_sec)
        raise DeadlineExpiredError(
            f"no response after {self.max_retries + 1} attempts: {self.last_error}"
        ) from self.last_error

    def call_within(self, fn: Callable[..., Any], *args: Any, budget_sec: float,
                    on_retry: Callable[[Exception | None], None] | None = None,
                    **kwargs: Any) -> Any:
        """Spend whole ``call`` rounds until ``budget_sec`` of wall clock is gone.

        ``call`` is a short burst - right for a peer that answers *slowly*, wrong
        for one that is *bouncing*. Measured against orcai-mj on 2026-08-13: their
        peer restarted every few seconds behind a healthy tunnel, so a 502 lasting
        ten seconds consumed all four attempts and killed our peer outright, at
        the handshake and again at every re-handshake. Four technical losses, none
        of them a real game.

        Still bounded, so rule #6 holds: patience with a deadline, not waiting
        forever. The budget is wall clock, not attempts, because the failure it
        exists for is measured in seconds of outage.
        """
        end = self._clock() + budget_sec
        while True:
            try:
                return self.call(fn, *args, **kwargs)
            except DeadlineExpiredError:
                if self._clock() >= end:
                    raise
                if on_retry is not None:
                    on_retry(self.last_error)
                self._sleep(self.backoff_sec)
