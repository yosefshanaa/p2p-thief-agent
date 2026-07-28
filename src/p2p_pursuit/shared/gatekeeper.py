"""Gatekeeper: three cumulative guards in front of every outgoing report (#28-29).

Quota Manager (daily cap) -> Token Bucket (rate) -> DOS Detector (loop-bug
anomaly => hard LOCKED, sacrificing the report to save the account).
Rate overflow is QUEUED (FIFO, bounded), never dropped - the guidelines'
backpressure rule: the queue absorbs bursts and drains as tokens refill.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .rate_limiter import TokenBucket

ALLOWED = "allowed"
REJECTED_QUOTA = "rejected: daily quota exhausted"
BLOCKED_RATE = "blocked: no rate token (back off)"
LOCKED_DOS = "LOCKED: send-anomaly detected (DOS guard)"
QUEUE_FULL = "backpressure: queue full"


@dataclass
class DosDetector:
    """A burst of sends inside a short window means a loop bug - lock everything."""

    window_sec: float = 10.0
    max_in_window: int = 8
    clock: Callable[[], float] = time.monotonic
    locked: bool = False
    _times: list[float] = field(default_factory=list)

    def note(self) -> None:
        now = self.clock()
        self._times = [t for t in self._times if now - t <= self.window_sec]
        self._times.append(now)
        if len(self._times) > self.max_in_window:
            self.locked = True


class Gatekeeper:
    def __init__(self, *, daily_quota: int, requests_per_minute: float,
                 burst_capacity: float | None = None, queue_depth: int = 100,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.daily_quota = daily_quota
        self.sent_today = 0
        self.bucket = TokenBucket(
            capacity=burst_capacity if burst_capacity is not None else max(
                2.0, requests_per_minute / 6),
            refill_rate=requests_per_minute / 60.0, clock=clock)
        self.dos = DosDetector(clock=clock)
        self.queue: deque[Any] = deque()
        self.queue_depth = queue_depth

    def check(self) -> str:
        """Run the three gates in order; only ALLOWED lets a request out (fail fast)."""
        if self.dos.locked:
            return LOCKED_DOS
        self.dos.note()
        if self.dos.locked:
            return LOCKED_DOS
        if self.sent_today >= self.daily_quota:
            return REJECTED_QUOTA
        if not self.bucket.allow():
            return BLOCKED_RATE
        self.sent_today += 1
        return ALLOWED

    def submit(self, item: Any) -> str:
        """Gate an outgoing item; rate overflow is queued FIFO, never dropped."""
        verdict = self.check()
        if verdict == BLOCKED_RATE:
            if len(self.queue) >= self.queue_depth:
                return QUEUE_FULL
            self.queue.append(item)
        return verdict

    def drain(self) -> list[Any]:
        """Release queued items as rate tokens refill (call periodically)."""
        released: list[Any] = []
        while self.queue and not self.dos.locked and \
                self.sent_today < self.daily_quota and self.bucket.allow():
            self.sent_today += 1
            released.append(self.queue.popleft())
        return released

    @classmethod
    def from_config(cls, rate_cfg: dict, *, daily_quota: int = 50, **kw) -> Gatekeeper:
        return cls(daily_quota=daily_quota,
                   requests_per_minute=rate_cfg.get("requests_per_minute", 30),
                   queue_depth=rate_cfg.get("queue_depth", 100), **kw)
