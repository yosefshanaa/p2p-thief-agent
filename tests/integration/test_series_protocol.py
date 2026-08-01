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


def test_an_inbound_commit_at_the_boundary_still_lands_in_the_right_role():
    """The race that voided sub-game 2 live (2026-08-01).

    The opponent starts its next sub-game the moment it finishes the last one,
    so its first commit can arrive while we are still completing the audit
    exchange - and an inbound commit advances the sub-game. If the role is only
    swapped by our series loop, the board is built for the wrong side: we
    announced "playing as thief" and then played it out as police, and both
    peers sat in a turn timeout. Whoever crosses the boundary first must pick
    the role.
    """
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    shared = make_shared()
    engine = TurnEngine("police", shared, make_peer("police", alternate_roles=True), seed=3)
    assert engine.role == "police"
    assert engine.own_pos == shared.cop_start

    engine.begin_sub_game(2)          # as an inbound commit would
    assert engine.role == "thief", "sub-game 2 is the alternated role"
    assert engine.own_pos == shared.thief_start, "the board must be built for that role"
    assert engine.next_mover == shared.first_mover

    engine.begin_sub_game(3)
    assert engine.role == "police" and engine.own_pos == shared.cop_start


def test_a_fixed_role_peer_is_untouched_by_the_boundary_rule():
    """Alternation is pair-negotiated and off by default; the published repos
    are role-fixed and must stay that way."""
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    engine = TurnEngine("police", make_shared(), make_peer("police"), seed=3)
    engine.begin_sub_game(2)
    assert engine.role == "police"


def test_the_audit_wait_is_bounded_when_we_rehandshake_each_sub_game():
    """A reference-derived peer negotiates the next sub-game the instant it
    finishes the last one and waits only ~60 s for our agreement. Our audit wait
    sits directly in front of that re-handshake, so a 360 s one does not merely
    delay us - it blows their window and costs the next sub-game entirely
    ("Opponent never sent its agreement", measured live 2026-08-01).
    """
    from types import SimpleNamespace

    from p2p_pursuit.peer import runtime_reports
    from tests.conftest import make_peer

    def rt(**peer_kw):
        return SimpleNamespace(deadline=SimpleNamespace(timeout_sec=180.0),
                               peer=make_peer("police", **peer_kw))

    assert runtime_reports._audit_wait(rt()) == 360.0, "a fixed-role series can be patient"
    bounded = runtime_reports._audit_wait(rt(handshake_per_sub_game=True))
    assert bounded == runtime_reports.REHANDSHAKE_AUDIT_WAIT
    assert bounded < 60.0, "must land inside their negotiate window"
