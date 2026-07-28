"""Reliability layer: state machine table, deadline retries, watchdog firing."""

import pytest

from p2p_pursuit.peer.deadline import DeadlineExpiredError, DeadlineTracker
from p2p_pursuit.peer.state_machine import (
    AWAITING_REVEAL,
    COMMITTING,
    COMPUTING_MOVE,
    TECHNICAL_LOSS,
    VERIFYING,
    WAITING_FOR_OPPONENT,
    GamePhaseMachine,
    IllegalTransitionError,
)
from p2p_pursuit.peer.watchdog import ALIVE, SHUTDOWN, Watchdog


def test_legal_turn_cycle():
    m = GamePhaseMachine()
    for state in (COMPUTING_MOVE, COMMITTING, AWAITING_REVEAL, VERIFYING,
                  WAITING_FOR_OPPONENT):
        m.transition(state)
    assert m.state == WAITING_FOR_OPPONENT


def test_illegal_transitions_raise():
    m = GamePhaseMachine()
    with pytest.raises(IllegalTransitionError):
        m.transition(COMMITTING)  # cannot skip COMPUTING_MOVE
    m.transition(COMPUTING_MOVE)
    with pytest.raises(IllegalTransitionError):
        m.transition(VERIFYING)


def test_technical_loss_is_terminal():
    m = GamePhaseMachine()
    m.transition(TECHNICAL_LOSS)
    with pytest.raises(IllegalTransitionError):
        m.transition(COMPUTING_MOVE)


def test_deadline_retries_then_expires():
    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky(*, timeout):
        calls["n"] += 1
        raise ConnectionError("down")

    d = DeadlineTracker(timeout_sec=1, max_retries=2, backoff_sec=5, sleep=sleeps.append)
    with pytest.raises(DeadlineExpiredError):
        d.call(flaky)
    assert calls["n"] == 3 and sleeps == [5, 5]


def test_deadline_success_after_retry():
    calls = {"n": 0}

    def flaky_then_ok(*, timeout):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("down")
        return {"ok": True}

    d = DeadlineTracker(timeout_sec=1, max_retries=3, backoff_sec=0, sleep=lambda s: None)
    assert d.call(flaky_then_ok) == {"ok": True}


def test_watchdog_fires_once_and_persists():
    now = {"t": 0.0}
    fired = []
    w = Watchdog(timeout_sec=60, on_freeze=lambda: fired.append(True), clock=lambda: now["t"])
    assert w.check() == ALIVE
    now["t"] = 30
    w.beat()
    now["t"] = 89
    assert w.check() == ALIVE
    now["t"] = 91
    assert w.check() == SHUTDOWN
    assert w.check() == SHUTDOWN  # stays down, callback fired exactly once
    assert fired == [True]
