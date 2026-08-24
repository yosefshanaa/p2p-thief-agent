"""The consensus send is not fire-once: it retries until acknowledged.

The failure this closes leaves no evidence behind. A single suppressed attempt
into a peer still assembling its own half produces silence on both sides - not a
mismatch either team can investigate, which is the one outcome a settlement
protocol must never produce quietly.
"""

from __future__ import annotations

import time
import types

from p2p_pursuit.peer import runtime_reports

NEVER = 10 ** 9


class _Bridge:
    """Accepts the envelope on the Nth attempt; hands back a digest when told."""

    def __init__(self, *, accept_on: int = 1, theirs: str | None = None,
                 theirs_after: int = 1) -> None:
        self.accept_on, self.attempts = accept_on, 0
        self._theirs, self._theirs_after = theirs, theirs_after
        self.waits = 0
        self.sent: list[dict] = []

    def submit_consensus(self, envelope, timeout=None):
        self.attempts += 1
        if self.attempts < self.accept_on:
            raise ConnectionError(f"not listening yet (attempt {self.attempts})")
        self.sent.append(envelope)
        return {"ok": True}

    def wait_for_consensus(self, timeout):
        self.waits += 1
        return self._theirs if self.waits >= self._theirs_after else None


def _rt(*, wait_sec: int = 6, retry_sec: int = 1):
    peer = types.SimpleNamespace(consensus_wait_sec=wait_sec,
                                 consensus_retry_sec=retry_sec)
    deadline = types.SimpleNamespace(call=lambda fn, *a, **k: fn(*a, **k))
    return types.SimpleNamespace(peer=peer, deadline=deadline, role="police")


def _push(rt, bridge):
    lines: list[str] = []
    theirs, delivered = runtime_reports._push_consensus(
        rt, bridge, {"sender": "police"}, lines.append)
    return theirs, delivered, lines


def test_a_refused_first_attempt_is_retried_not_swallowed():
    bridge = _Bridge(accept_on=3, theirs="b" * 64, theirs_after=1)
    theirs, delivered, lines = _push(_rt(), bridge)
    assert bridge.attempts >= 3
    assert bridge.sent, "the envelope was never actually delivered"
    assert (theirs, delivered) == ("b" * 64, True)
    assert any("attempt" in line for line in lines)


def test_their_digest_arriving_first_does_not_stop_our_send():
    """The two directions are independent: they can answer before they receive.

    Stopping when theirs lands would leave THEM unsettled for exactly the reason
    this retry exists, and their §16 requires a positive acknowledgement of ours.
    """
    bridge = _Bridge(accept_on=4, theirs="e" * 64, theirs_after=1)
    theirs, delivered, _ = _push(_rt(), bridge)
    assert (theirs, delivered) == ("e" * 64, True)
    assert bridge.sent, "we stopped sending as soon as theirs arrived"
    assert bridge.attempts >= 4


def test_it_stops_sending_once_acknowledged():
    """A peer that took it must not be sent it again for the rest of the window."""
    bridge = _Bridge(accept_on=1, theirs="c" * 64, theirs_after=3)
    theirs, delivered, _ = _push(_rt(), bridge)
    assert (theirs, delivered) == ("c" * 64, True)
    assert bridge.attempts == 1
    assert bridge.waits == 3


def test_their_digest_ends_the_loop_once_ours_is_in():
    bridge = _Bridge(accept_on=1, theirs="d" * 64, theirs_after=1)
    theirs, delivered, _ = _push(_rt(), bridge)
    assert (theirs, delivered) == ("d" * 64, True)
    assert bridge.waits == 1


def test_a_window_that_expires_returns_none_and_never_raises():
    """The caller's contract: this costs the confirmation, never the series."""
    bridge = _Bridge(accept_on=NEVER, theirs=None)
    theirs, delivered, lines = _push(_rt(wait_sec=2, retry_sec=1), bridge)
    assert (theirs, delivered) == (None, False)
    assert bridge.attempts > 1
    assert any("NEVER acknowledged" in line for line in lines)


def test_a_digest_we_could_not_answer_is_still_returned():
    """Received-but-unanswerable is evidence, not something to discard."""
    bridge = _Bridge(accept_on=NEVER, theirs="f" * 64, theirs_after=1)
    theirs, delivered, lines = _push(_rt(wait_sec=2, retry_sec=1), bridge)
    assert theirs == "f" * 64
    assert delivered is False
    assert any("NEVER acknowledged" in line for line in lines)


def test_delivered_but_silent_says_so_distinctly():
    bridge = _Bridge(accept_on=1, theirs=None)
    theirs, delivered, lines = _push(_rt(wait_sec=2, retry_sec=1), bridge)
    assert (theirs, delivered) == (None, True)
    assert any("no consensus envelope" in line for line in lines)


def test_the_send_deadline_is_the_same_clock_as_the_wait():
    """Not two timers: a retry loop outliving `consensus_wait_sec` would block
    the result artifact behind a peer that is simply gone."""
    bridge = _Bridge(accept_on=NEVER, theirs=None)
    started = time.monotonic()
    theirs, delivered, _ = _push(_rt(wait_sec=2, retry_sec=1), bridge)
    elapsed = time.monotonic() - started
    assert (theirs, delivered) == (None, False)
    assert elapsed < 6, f"ran {elapsed:.1f}s past a 2s window"
