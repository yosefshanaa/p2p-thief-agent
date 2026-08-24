"""A bouncing opponent must cost a pause, not the match.

Measured live against orcai-mj on 2026-08-13. Their tunnel was healthy and their
peer process was restarting every few seconds, so the endpoint alternated 200 /
502 within one poll interval. A 502 that outlasts four attempts (~20 s) took the
whole match down twice over:

  * at connect, our peer died on an unhandled DeadlineExpiredError traceback,
    after `wait_until_up` had already succeeded - reachable is not ready;
  * at every per-sub-game re-handshake, producing four technical losses in a row,
    none of which was a played game.

In a counted match either one is unrecoverable and scores 0/0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2p_pursuit.peer import series_protocol
from p2p_pursuit.peer.deadline import DeadlineExpiredError, DeadlineTracker
from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent


def tracker(clock_ref, sleeps, *, max_retries=1):
    """A tracker whose clock only advances when it sleeps - no wall-clock waiting."""

    def sleep(sec):
        sleeps.append(sec)
        clock_ref["t"] += sec

    return DeadlineTracker(timeout_sec=1, max_retries=max_retries, backoff_sec=5,
                           sleep=sleep, clock=lambda: clock_ref["t"])


def test_call_within_survives_an_outage_longer_than_one_burst():
    clock, sleeps, calls = {"t": 0.0}, [], {"n": 0}

    def bouncing(*, timeout):
        calls["n"] += 1
        if calls["n"] < 7:          # ~3 bursts' worth of 502s
            raise ConnectionError("502 Bad Gateway")
        return {"ok": True}

    d = tracker(clock, sleeps)
    assert d.call_within(bouncing, budget_sec=90) == {"ok": True}
    assert calls["n"] == 7, "it must keep spending rounds, not stop at the first burst"


def test_call_within_is_still_bounded():
    clock, sleeps = {"t": 0.0}, []

    def always_down(*, timeout):
        raise ConnectionError("502 Bad Gateway")

    d = tracker(clock, sleeps)
    with pytest.raises(DeadlineExpiredError):
        d.call_within(always_down, budget_sec=30)
    assert clock["t"] >= 30, "patience must end - rule #6 forbids waiting forever"


def test_call_within_reports_each_failed_round():
    clock, seen = {"t": 0.0}, []
    calls = {"n": 0}

    def flaky(*, timeout):
        calls["n"] += 1
        if calls["n"] < 5:
            raise ConnectionError("502")
        return {"ok": True}

    d = tracker(clock, [])
    d.call_within(flaky, budget_sec=90, on_retry=seen.append)
    assert seen, "an operator watching the log must see the retry, not silence"


def test_connect_returns_false_instead_of_crashing(tmp_path, monkeypatch):
    """The observed traceback: DeadlineExpiredError escaping connect()."""
    rt = PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path, num_games=6)
    rt.peer = type(rt.peer)(**{**rt.peer.__dict__, "handshake_budget_sec": 20})

    class DeadLink:
        opponent_already_contacted = None

        def health(self, timeout=5):
            return {"ok": True}          # reachable...

        def handshake(self, payload, timeout=None):
            raise ConnectionError("502 Bad Gateway")   # ...but never ready

    clock = {"t": 0.0}

    def sleep(sec):
        clock["t"] += sec

    rt.deadline = DeadlineTracker(timeout_sec=1, max_retries=1, backoff_sec=5,
                                  sleep=sleep, clock=lambda: clock["t"])
    monkeypatch.setattr("p2p_pursuit.peer.runtime_connect.wait_until_up", lambda link: True)

    assert rt.connect(DeadLink()) is False


def test_rehandshake_survives_a_blip_and_plays_the_sub_game(tmp_path, monkeypatch):
    rt = PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path, num_games=6)
    rt.peer = type(rt.peer)(**{**rt.peer.__dict__, "handshake_per_sub_game": True,
                               "rehandshake_budget_sec": 90})
    clock, calls = {"t": 0.0}, {"n": 0}

    def sleep(sec):
        clock["t"] += sec

    rt.deadline = DeadlineTracker(timeout_sec=1, max_retries=1, backoff_sec=5,
                                  sleep=sleep, clock=lambda: clock["t"])

    class Blippy:
        def handshake(self, payload, timeout=None):
            calls["n"] += 1
            if calls["n"] < 4:
                raise ConnectionError("502 Bad Gateway")
            # A usable agreement: our terms, the opposite role (#57).
            return dict(rt.service.my_handshake, sub_game=payload["sub_game"],
                        role="thief")

    rt.link = Blippy()
    rt.engine.begin_sub_game(2)
    assert series_protocol.rehandshake_if_needed(rt, 2, lambda m: None) is True
    assert rt.engine.end is None, "a survivable blip must not file a technical loss"
