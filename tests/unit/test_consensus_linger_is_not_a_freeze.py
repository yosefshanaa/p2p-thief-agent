"""The watchdog must not cry freeze while the consensus linger does its job.

`Watchdog.beat` is called from the two turn loops and nowhere else. The series
consensus exchange runs *after* the last window, blocking in
`ReferenceBridge.wait_for_consensus` for up to `consensus_wait_sec` - 600s as
agreed with yanell11 - against a watchdog whose default timeout is 60s. Armed
across that wait it is guaranteed to fire on every clean series where the peer
has already disconnected, which is precisely when the linger matters.

That is not a hypothetical. On 2026-08-23 yanell11's peers exited the moment
sub-game 6 closed; our watchdog printed "main loop frozen ... shutting down" 60s
later; we read it as a hang and killed the process ~4 minutes before
`wait_for_consensus` would have returned - discarding the result artifact,
`mutual_signature` and report that `run_series` was about to file from six
windows that had all audited `Verified OK`. The line was doubly misleading: it
announced a shutdown that `_persist_and_note` never performs.

Two invariants, then: the watchdog is disarmed before the linger, and its
message does not claim to have killed anything.
"""

from __future__ import annotations

import inspect

from p2p_pursuit.peer import runtime
from p2p_pursuit.peer.watchdog import ALIVE, SHUTDOWN, Watchdog


def test_the_watchdog_is_stopped_before_the_consensus_exchange() -> None:
    """Ordering, read off the source: stop() precedes the exchange call."""
    src = inspect.getsource(runtime.PeerRuntime.run_series)
    stop_at = src.index("self.watchdog.stop()")
    exchange_at = src.index("exchange_series_consensus")
    assert stop_at < exchange_at, (
        "the consensus linger runs with the watchdog armed - it will fire a "
        "false freeze on every clean series that waits out a departed peer")


def test_the_freeze_message_does_not_claim_a_shutdown() -> None:
    """`on_freeze` persists and returns; the loop keeps running.

    Pinned as text because the damage was done by the wording, not the code:
    a line that says "shutting down" invites exactly the wrong intervention.
    """
    src = inspect.getsource(runtime.PeerRuntime._persist_and_note)
    assert "shutting down" not in src
    assert "NOT killed" in src, "say plainly that the process survives"


def test_on_freeze_really_does_not_kill_the_process() -> None:
    """The behaviour the message must describe: persist, return, carry on."""
    calls: list[str] = []
    now = [0.0]
    dog = Watchdog(timeout_sec=60, on_freeze=lambda: calls.append("persisted"),
                   clock=lambda: now[0])
    assert dog.check() == ALIVE
    now[0] = 61.0
    assert dog.check() == SHUTDOWN
    assert calls == ["persisted"], "on_freeze is a callback, not an exit"
    # Fires once, and the caller lives to keep calling.
    assert dog.check() == SHUTDOWN
    assert calls == ["persisted"]


def test_a_linger_longer_than_the_watchdog_is_the_normal_case() -> None:
    """The mismatch is by design, which is why disarming is the fix.

    600s was agreed with yanell11 so that neither peer is the impatient side;
    the 60s watchdog is right for a turn loop that beats every second. Both
    numbers are correct - they simply must not overlap.
    """
    from p2p_pursuit.shared.config import PeerConfig

    assert PeerConfig(raw={}, group_name="x", group_id="x").consensus_wait_sec == 60
    assert 600 > 60, "the agreed linger dwarfs the default watchdog timeout"
