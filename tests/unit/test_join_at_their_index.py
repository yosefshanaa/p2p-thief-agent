"""Joining a series where the opponent already is.

Two peers that both advance on failure and both insist on their own index cannot
resynchronise by restarting - the side that restarts is behind again by its own
boot time and the gap changes sign. Measured live against uoh-sqak 2026-08-10:
their peer moved 1 -> 3 in the two minutes ours took to come up, twice running.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def runtime(tmp_path):
    return PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path, num_games=6)


def test_joins_forward_when_the_opponent_is_ahead(runtime):
    runtime._join_at_their_index({"sub_game_number": 3})
    assert runtime.start_index == 3


def test_never_pulls_the_opponent_backwards(runtime):
    """An index they have settled is not replayable - asking is what deadlocks."""
    runtime.start_index = 4
    runtime._join_at_their_index({"sub_game_number": 2})
    assert runtime.start_index == 4


def test_refuses_to_join_a_finished_series(runtime):
    runtime._join_at_their_index({"sub_game_number": 9})
    assert runtime.start_index == 1, "sub-game 9 of a 6-sub-game series is not joinable"


def test_a_missing_or_malformed_index_changes_nothing(runtime):
    for agreement in ({}, {"sub_game_number": None}, {"sub_game_number": "3"}, None):
        runtime._join_at_their_index(agreement)
        assert runtime.start_index == 1


def test_the_series_loop_starts_where_we_joined(runtime, monkeypatch):
    played: list[int] = []
    monkeypatch.setattr(runtime, "play_sub_game", played.append)
    monkeypatch.setattr("p2p_pursuit.peer.runtime_reports.finish_sub_game",
                        lambda rt, n, log: {"index": n})
    monkeypatch.setattr(runtime, "build_result", lambda: {})
    runtime.start_index = 4
    runtime.run_series()
    assert played == [4, 5, 6], "a joined series must not replay what it skipped"
