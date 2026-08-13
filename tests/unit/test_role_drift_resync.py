"""A drifted index must cost one sub-game, not the series.

Measured against orcai-mj 2026-08-13. Their cop went silent for sub-game 1, the
two series indices drifted apart, and because the role each peer plays under
alternation is a function of the index, every other sub-game then collided:

    sub-game 3: technical_loss (both peers claim role 'thief')
    sub-game 5: technical_loss (both peers claim role 'thief')

All six sub-games died, 0-0. Nothing in a refused re-handshake ever brings the
indices back together, so the failure is unrecoverable by construction - and in
a counted match, sealed.

We already join the opponent's index when a series *starts*. This is the same
principle mid-series, expressed in the one term that must agree for a sub-game
to be playable: the two roles being complementary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.peer import series_protocol
from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def runtime(tmp_path):
    rt = PeerRuntime("thief", BASE / "config" / "thief", out_dir=tmp_path, num_games=6)
    rt.peer = type(rt.peer)(**{**rt.peer.__dict__, "handshake_per_sub_game": True,
                               "alternate_roles": True})
    return rt


class Link:
    """An opponent that declares the same role we were about to play."""

    def __init__(self, runtime, their_role):
        self.rt, self.their_role = runtime, their_role
        self.seen: list[dict] = []

    def handshake(self, payload, timeout=None):
        self.seen.append(dict(payload))
        return dict(self.rt.service.my_handshake, role=self.their_role,
                    sub_game=payload["sub_game"])


def test_a_role_collision_is_resolved_instead_of_forfeited(runtime):
    runtime.engine.begin_sub_game(3)
    mine = runtime.engine.role
    runtime.link = Link(runtime, mine)          # they claim the same role

    assert series_protocol.rehandshake_if_needed(runtime, 3, lambda m: None) is True
    assert runtime.engine.end is None, "a resolvable collision must not file a loss"
    assert runtime.engine.role != mine, "we must take the other side"


def test_the_starting_cell_matches_the_role_we_took(runtime):
    runtime.engine.begin_sub_game(3)
    runtime.link = Link(runtime, runtime.engine.role)

    series_protocol.rehandshake_if_needed(runtime, 3, lambda m: None)

    shared = runtime.engine.shared
    expected = shared.cop_start if runtime.engine.role == POLICE else shared.thief_start
    assert tuple(runtime.engine.own_pos) == tuple(expected), (
        "swapping role without re-entering the sub-game would leave us standing "
        "on the other role's start square")


def test_our_declared_role_matches_what_we_will_play(runtime):
    runtime.engine.begin_sub_game(3)
    runtime.link = Link(runtime, runtime.engine.role)

    series_protocol.rehandshake_if_needed(runtime, 3, lambda m: None)

    assert runtime.service.my_handshake["role"] == runtime.engine.role, (
        "the agreement we leave on record must state the role we actually play")


def test_a_fixed_role_series_is_untouched(runtime):
    """Without alternation a role collision is a real disagreement, not drift."""
    runtime.peer = type(runtime.peer)(**{**runtime.peer.__dict__,
                                         "alternate_roles": False})
    runtime.engine.begin_sub_game(2)
    mine = runtime.engine.role
    runtime.link = Link(runtime, mine)

    assert series_protocol.rehandshake_if_needed(runtime, 2, lambda m: None) is False
    assert runtime.engine.role == mine
    assert runtime.engine.end is not None


def test_complementary_roles_are_left_alone(runtime):
    runtime.engine.begin_sub_game(3)
    mine = runtime.engine.role
    other = POLICE if mine == THIEF else THIEF
    runtime.link = Link(runtime, other)

    assert series_protocol.rehandshake_if_needed(runtime, 3, lambda m: None) is True
    assert runtime.engine.role == mine, "no drift, nothing to adopt"
