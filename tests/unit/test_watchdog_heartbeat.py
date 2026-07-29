"""The watchdog must not kill a healthy peer that is legitimately waiting.

Found by the live tunnel drill (GATE M5): the agreed turn timeout is 180s
but the watchdog fires at 60s, and the peer blocked the whole turn wait in
one call without a heartbeat. Over localhost an opponent always answers
inside 60s so it never triggered; over a real tunnel our own peer
self-terminated mid-match - a self-inflicted technical loss.
"""

import contextlib

from p2p_pursuit.peer.deadline import DeadlineTracker


class _Recorder:
    """Stand-in watchdog counting heartbeats."""

    def __init__(self, timeout_sec: float = 60.0) -> None:
        self.timeout_sec = timeout_sec
        self.beats = 0

    def beat(self) -> None:
        self.beats += 1


def test_deadline_retries_emit_heartbeats():
    """A full retry budget (4 attempts x 30s + backoff) far exceeds the 60s
    watchdog, so the tracker must beat between attempts."""
    dog = _Recorder()
    tracker = DeadlineTracker(timeout_sec=30, max_retries=3, backoff_sec=0,
                              sleep=lambda _s: None, on_attempt=dog.beat)

    def always_fails(*_a, **_k):
        raise ConnectionError("tunnel down")

    with contextlib.suppress(Exception):
        tracker.call(always_fails)
    assert dog.beats >= 4, f"expected a heartbeat per attempt, got {dog.beats}"


def test_deadline_on_attempt_is_optional():
    tracker = DeadlineTracker(timeout_sec=1, max_retries=0, backoff_sec=0,
                              sleep=lambda _s: None)
    assert tracker.call(lambda *a, **k: "ok") == "ok"
