"""A door-per-role peer's index is that door's next window, not the series'.

`PeerRuntime._join_at_their_index` exists because uoh-sqak's peer genuinely
advanced 1 -> 3 while ours booted (2026-08-10): a peer that restarts behind the
other can never catch up by insisting on its own index, so it joins where the
opponent already is. That peer ran ONE process, so its `sub_game_number` really
was the series position.

yanell11 run a rule-1 split - two processes, two doors - and under alternation
their cop's first window is series window 2. A cop that has played nothing
truthfully declares `sub_game_number: 2`. Read as "window 1 is settled" we skip
window 1 entirely, and their thief is left holding it.

That cost three runs on 2026-08-23. Worse, the damage compounds: with window 1
skipped, their thief's window-1 turns arrive naming the role we now hold, our
role-collision handler reads a drifted index, and `retarget_link` points us at
the door of the half that is not playing - a permanent stall. Every symptom was
reported to them as stale state on their side. Their peers were correct.

There is no downstream repair available: their turn messages carry no sub-game
field at all (`interop_codec.to_turn_message` emits step/sender/hint/smell_grid/
commit/timestamp/barrier_placed/capture_claim/claim_response/win_claim), so a
late window-1 turn cannot be told from a current one. Declining the jump is the
entire fix, and it is scoped to peers we know serve a door per role - which
leaves the uoh-sqak behaviour exactly as it was for every single-door peer.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from p2p_pursuit.infra.interop_codec import to_turn_message
from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent
DOORS = {"police": "https://their-cop.example/mcp",
         "thief": "https://their-thief.example/mcp"}


@pytest.fixture
def rt(tmp_path) -> PeerRuntime:
    return PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path, seed=1)


def test_a_split_peers_declared_index_is_not_joined(rt) -> None:
    """The regression: their cop says 2 because 2 is its first window."""
    rt.peer = dataclasses.replace(rt.peer, opponent_doors=DOORS)
    rt._join_at_their_index({"sub_game_number": 2})
    assert rt.start_index == 1, (
        "joined at their cop's first window and skipped window 1 - the failure "
        "that stalled three runs against yanell11")


def test_a_single_door_peer_is_still_joined(rt) -> None:
    """uoh-sqak's fix is untouched: one process, one index, still adopted."""
    assert not rt.peer.opponent_doors
    rt._join_at_their_index({"sub_game_number": 3})
    assert rt.start_index == 3


def test_the_guard_is_the_doors_and_not_the_alternation_flag(rt) -> None:
    """Alternation alone does not make an index per-door - a single-door peer
    that alternates still reports the series position."""
    rt.peer = dataclasses.replace(rt.peer, alternate_roles=True, opponent_doors={})
    rt._join_at_their_index({"sub_game_number": 4})
    assert rt.start_index == 4


def test_backwards_and_out_of_range_are_still_refused(rt) -> None:
    rt._join_at_their_index({"sub_game_number": 1})
    assert rt.start_index == 1
    rt._join_at_their_index({"sub_game_number": rt.num_games + 1})
    assert rt.start_index == 1
    rt._join_at_their_index({"sub_game_number": "2"})
    assert rt.start_index == 1


def test_their_turn_carries_no_sub_game_so_no_downstream_repair_exists() -> None:
    """Why the fix has to be here and cannot be a late-turn filter.

    Our own sealed payload carries `sub_game` AND `sub_game_number` precisely so
    a peer can bucket our reveal by content. Theirs carries neither, so once we
    are on the wrong window their traffic is unattributable.
    """
    wire = to_turn_message({"step": 3, "role": "thief", "hint": "", "scent": [],
                            "barrier": None, "hash": "ab" * 32})
    assert "sub_game" not in wire and "sub_game_number" not in wire
