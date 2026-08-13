"""Two peers must never both wait for each other.

Measured against orcai-mj 2026-08-13: both sides' 180 s timers expired at the
same step count, twice. `next_mover` was a flag written from two threads -
`_send_package` calls `link.reveal` outside the lock, so their reveal could
arrive mid-flight, set the flag to us, and then be overwritten by our own
`sent_reveal()` setting it back to them. Each peer then waited for a move the
other had already made. 0/0, and in a counted match sealed.

Turn ownership is now derived from the step counts, which cannot be clobbered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent


def engine_for(role: str, tmp_path):
    rt = PeerRuntime(role, BASE / "config" / role, out_dir=tmp_path, num_games=6)
    eng = rt.engine
    eng.begin_sub_game(1)
    return eng


def test_first_mover_opens_the_sub_game(tmp_path):
    thief = engine_for("thief", tmp_path)
    police = engine_for("police", tmp_path)
    assert thief.shared.first_mover == "thief"
    assert thief.my_turn is True
    assert police.my_turn is False, "both peers cannot be on turn at once"


def test_the_reveal_that_arrives_mid_send_is_not_lost(tmp_path):
    """The exact race: their reveal lands while our own send is in flight."""
    thief = engine_for("thief", tmp_path)
    thief.build_own_step()                 # my_steps 1, theirs 0 -> waiting
    thief.sent_commit()                    # the real order: commit, then reveal
    assert thief.my_turn is False

    # Their reveal arrives first...
    thief.on_reveal({"hash": "h", "step": 1, "pos_after": [0, 0], "move": "STAY",
                     "barrier": None, "hint": "", "scent": [[0.0] * 7 for _ in range(7)]})
    # ...and only then does our own in-flight send complete.
    thief.sent_reveal()

    assert thief.my_turn is True, (
        "the counts say it is our move; a flag written by the later of two "
        "concurrent events would say otherwise and deadlock both peers")


def test_second_mover_waits_until_it_is_one_behind(tmp_path):
    police = engine_for("police", tmp_path)
    assert police.my_turn is False
    police.on_reveal({"hash": "h", "step": 1, "pos_after": [3, 3], "move": "STAY",
                      "barrier": None, "hint": "", "scent": [[0.0] * 7 for _ in range(7)]})
    assert police.my_turn is True
    police.build_own_step()
    assert police.my_turn is False, "level counts mean the first mover is on turn"


def test_a_finished_sub_game_is_nobody_s_turn(tmp_path):
    thief = engine_for("thief", tmp_path)
    thief.declare_technical(thief.other, "turn timeout (180s)")
    assert thief.my_turn is False


@pytest.mark.parametrize("steps", [0, 1, 5, 17, 34])
def test_exactly_one_peer_is_ever_on_turn(tmp_path, steps):
    """The property that makes a mutual stall impossible, at every step count."""
    thief = engine_for("thief", tmp_path)
    police = engine_for("police", tmp_path)
    for eng, mine, theirs in ((thief, steps, steps), (police, steps, steps)):
        eng.my_steps, eng.opp_steps = mine, theirs
    assert thief.my_turn != police.my_turn or (thief.my_turn and not police.my_turn)
    assert thief.my_turn is True and police.my_turn is False

    thief.my_steps, thief.opp_steps = steps + 1, steps
    police.my_steps, police.opp_steps = steps, steps + 1
    assert thief.my_turn is False and police.my_turn is True
