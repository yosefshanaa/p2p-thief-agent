"""A refused re-handshake must not inherit the previous sub-game's result.

Measured live against uoh-sqak 2026-08-10: sub-game 1 ended in a real capture,
the sub-game 2 re-handshake was refused, and the refusal path returned before
the engine was ever reset - so sub-games 2 and 3 were both filed as captures at
the same cell, neither of which was played. Nothing reached the lecturer because
the friendly ran in draft mode, but in a counted match that is an invented
result inside a signed report.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2p_pursuit.domain.scoring import TECHNICAL_LOSS
from p2p_pursuit.peer import series_protocol
from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def runtime(tmp_path):
    rt = PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path, num_games=6)
    rt.peer = type(rt.peer)(**{**rt.peer.__dict__, "handshake_per_sub_game": True})
    return rt


def test_refusal_does_not_file_the_previous_sub_games_ending(runtime, monkeypatch):
    engine = runtime.engine
    engine.begin_sub_game(1)
    engine.declare_technical("thief", "captured at (5, 6)")
    assert engine.end is not None, "sub-game 1 needs an ending that could be inherited"

    # Sub-game 2: the opponent refuses / disagrees at the re-handshake.
    monkeypatch.setattr(series_protocol, "_rehandshake",
                        lambda rt, n, log_fn: (rt.engine.declare_technical(
                            rt.engine.other, "re-handshake refused: terms"), False)[1])
    runtime.play_sub_game(2)

    assert engine.sub_game == 2, "the engine must be reset onto the refused sub-game"
    assert engine.end is not None
    assert engine.end.ending == TECHNICAL_LOSS, (
        f"a refused sub-game must be a technical loss, not {engine.end.ending!r} "
        "inherited from the sub-game before it")
    assert "capture" not in (engine.end.cause or "").lower()


def test_role_is_taken_before_state_is_built(runtime):
    """start_sub_game reads the role to pick starting cells and the first mover."""
    runtime.peer = type(runtime.peer)(**{**runtime.peer.__dict__,
                                         "alternate_roles": True,
                                         "handshake_per_sub_game": False})
    series_protocol.take_role(runtime, 2, lambda *_: None)
    runtime.service.ensure_sub_game(2)
    engine = runtime.engine
    assert engine.role == "thief", "sub-game 2 alternates away from our natural police"
    assert engine.own_pos == runtime.shared.thief_start, (
        "starting cell must follow the role taken for THIS sub-game")
    assert engine.next_mover == runtime.shared.first_mover
