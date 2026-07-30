"""Role alternation and per-sub-game re-handshake.

Both are pair-negotiated series conventions that the book leaves open, and both
break a match only from sub-game 2 - so these tests deliberately run TWO
sub-games. A one-sub-game test would pass against a broken implementation,
which is precisely how the live warm-up missed them (RUNBOOK 3b).
"""

from __future__ import annotations

import dataclasses

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.peer.series_protocol import role_for
from p2p_pursuit.peer.turn_engine import TurnEngine
from tests.conftest import make_peer, make_shared


def test_role_for_matches_the_reference_convention():
    """Natural on odd, opposite on even - their sdk/series.py role_for()."""
    assert role_for(POLICE, 1) == POLICE
    assert role_for(POLICE, 2) == THIEF
    assert role_for(POLICE, 3) == POLICE
    assert role_for(THIEF, 2) == POLICE
    assert [role_for(THIEF, n) for n in range(1, 7)] == [
        THIEF, POLICE, THIEF, POLICE, THIEF, POLICE]


def test_two_peers_alternating_never_claim_the_same_role():
    """The collision that voids a counted match from sub-game 2."""
    for n in range(1, 7):
        assert role_for(POLICE, n) != role_for(THIEF, n)


def test_set_role_swaps_brain_and_start_cell():
    shared = make_shared()
    engine = TurnEngine("police", shared, make_peer("police"), seed=1)
    assert engine.own_pos == shared.cop_start
    police_brain = engine.brain

    engine.set_role(THIEF)
    engine.start_sub_game(2)
    assert engine.role == THIEF
    assert engine.other == POLICE
    assert engine.own_pos == shared.thief_start
    assert engine.brain is not police_brain, "the thief must not think like a cop"

    engine.set_role(POLICE)
    engine.start_sub_game(3)
    assert engine.own_pos == shared.cop_start
    assert engine.brain is police_brain, "brains are cached, not rebuilt each swap"


def test_alternating_series_plays_both_sides_cleanly():
    """Two sub-games, sides swapped in the middle, both audited."""
    from p2p_pursuit.peer.local_match import play_sub_game

    shared = make_shared()
    police = TurnEngine("police", shared, make_peer("police"), seed=4)
    thief = TurnEngine("thief", shared, make_peer("thief"), seed=5)
    play_sub_game(police, thief)
    assert police.end is not None and thief.end is not None

    # sub-game 2: both peers swap sides, as an alternating opponent expects
    police.set_role(THIEF)
    thief.set_role(POLICE)
    police.start_sub_game(2)
    thief.start_sub_game(2)
    assert police.own_pos == shared.thief_start
    assert thief.own_pos == shared.cop_start
    play_sub_game(thief, police)  # the swapped peers, in their new seats
    assert police.end is not None and thief.end is not None


def test_config_reads_both_series_switches():
    from pathlib import Path

    from p2p_pursuit.shared.config import load_peer

    peer = load_peer(Path("config/police/game.toml"))
    assert peer.alternate_roles is False, "off by default: our repos are role-fixed"
    assert peer.handshake_per_sub_game is False


def test_alternation_is_off_unless_configured():
    """A peer must not start swapping sides because an opponent happens to."""
    cfg = make_peer("police")
    assert cfg.alternate_roles is False
    swapped = dataclasses.replace(cfg, alternate_roles=True)
    assert swapped.alternate_roles is True
