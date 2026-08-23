"""A match is six sub-games, and the thief may not walk into the same grave twice.

The archive is unambiguous about why this exists. Of 22 archived series and 67
thief sub-games, 38 ended in capture (57%); **eight series lost every thief
window, and six of those lost them at the identical step** - vibecode at step
14 on [6, 5] in three friendlies running, najamjad at step 30, uoh-ay26 at step
10 on [5, 5], orcai-mj at step 16. Five of the six died on one repeated cell.

(An earlier version of this file said "ten series ... vibecode at 28, najamjad
at 31, orcai-mj at 17, uoh-ay26 at 20". Those came from a survey that mixed two
step conventions - counting both peers' turns for some series and one peer's for
others - and every number in it was wrong. The figures above are `my_steps` read
straight from `result` in each sealed log, which is the only unambiguous field.)

Mixing does not fix it and was never going to: it varies the road, and a police
that funnels gathers every road to the same cell. Measured against the cage
transcript, the thief took three different routes and died on [2, 4] at step 31
in all six sub-games. What the vector was missing is not randomness - it is the
one fact no per-turn term can hold: *what happened in the previous sub-game*.
"""

from __future__ import annotations

import random

import pytest

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.brains_base import BrainView
from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.domain.scoring import CAPTURE, SURVIVAL
from p2p_pursuit.learn import population
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from p2p_pursuit.strategy.thief_brain import GRAVE_TAIL, ThiefBrain

SIZE = 7
#: najamjad's cage was played under the counted contract's physics, and the
#: default is `book_v1`. This is not a detail: under `book_v1` the cage takes
#: our thief **0 times in 48**, so a ratchet test run without these three lines
#: passes on a brain with no memory at all. The first version of this file did
#: exactly that - see `test_mixing_margins_are_decided` for the same mistake
#: caught in the same week.
COUNTED_PHYSICS = {
    "P2P_SCENT_MODEL": "subtractive_chebyshev_v1",
    "P2P_SCENT_SERVE_BEFORE_DECAY": "true",
    "P2P_DOCTRINE": "config/doctrine-subtractive.json",
}


@pytest.fixture
def counted(monkeypatch):
    """The lab peer config rebuilt under the physics the cage was played on.

    `QUIET` and `active()` are resolved at import time, so setting the
    environment is not enough - both are re-derived here inside the patch.
    """
    for key, value in COUNTED_PHYSICS.items():
        monkeypatch.setenv(key, value)
    from p2p_pursuit.learn.arena import default_shared
    from p2p_pursuit.shared.config import PeerConfig, apply_env_overrides
    from p2p_pursuit.strategy.params import active

    peer = apply_env_overrides(PeerConfig(raw={}, group_name="lab", group_id="lab"))
    assert peer.scent_model == "subtractive_chebyshev_v1"
    return default_shared(), peer, active()


def view(pos=(3, 3), step=1, sub_game=1) -> BrainView:
    return BrainView(
        role=THIEF, sub_game=sub_game, step=step, own_pos=pos, board=Board(SIZE, set()),
        belief=BeliefMap(size=SIZE), opp_scent=[[0.0] * SIZE for _ in range(SIZE)],
        own_scent=[[0.0] * SIZE for _ in range(SIZE)], barriers_used=0,
        barrier_quota=14, steps_remaining=30, survival_threshold=35,
        trust=1.0, map_area="urban", rng=random.Random(0))


def test_a_short_sub_game_buries_the_cell_it_ended_on():
    """The brain is never told it was caught, so it infers it from the step count."""
    brain = ThiefBrain()
    brain._pick_move(view(pos=(2, 4), step=1, sub_game=1))
    brain._pick_move(view(pos=(2, 4), step=9, sub_game=1))       # ended at step 9
    assert brain._graves == []
    brain._pick_move(view(pos=(3, 3), step=1, sub_game=2))       # a new sub-game
    assert brain._graves, "a sub-game that stopped at step 9 of 35 was not a capture?"
    assert brain._graves[0][0] == (2, 4), "buried a cell we never stood on"


def test_surviving_a_sub_game_buries_nothing():
    brain = ThiefBrain()
    for step in range(1, 36):
        brain._pick_move(view(pos=(3, 3), step=step, sub_game=1))
    brain._pick_move(view(pos=(3, 3), step=1, sub_game=2))
    assert brain._graves == [], "survival was recorded as a death"


def test_the_first_sub_game_has_no_grave_to_avoid():
    brain = ThiefBrain()
    brain._pick_move(view(sub_game=1, step=1))
    assert brain._graves == []


def test_only_the_death_cell_is_buried():
    """A tail of 2 scores exactly as badly as no memory at all - `ThiefBrain._bury`."""
    assert GRAVE_TAIL == 1


def test_a_weight_of_zero_switches_the_whole_term_off():
    """`w_grave` is a doctrine key, so a physics that does not want it can say so."""
    from dataclasses import replace

    from p2p_pursuit.strategy.params import active

    brain = ThiefBrain(replace(active(), w_grave=0.0))
    brain._pick_move(view(pos=(2, 4), step=1, sub_game=1))
    brain._pick_move(view(pos=(2, 4), step=9, sub_game=1))
    brain._pick_move(view(pos=(3, 3), step=1, sub_game=2))
    assert brain._graves, "the burial is unconditional; only the penalty is weighted"


def test_a_series_against_the_cage_stops_dying_in_the_same_cell(counted):
    """The ratchet. Without the grave term this is 6/6 captured, every seed.

    Measured over 8 seeds at 48/48 before and 8/48 after; two seeds are enough
    to fail loudly here without making the unit suite pay for forty-eight
    sub-games.
    """
    shared, peer, doctrine = counted
    member = population.build(("najamjad-cage",))["najamjad-cage"]
    caught = played = 0
    for seed in (72000, 72001):
        police = TurnEngine(POLICE, shared, peer, brain=member.make(POLICE), seed=seed * 2)
        thief = TurnEngine(THIEF, shared, peer, brain=ThiefBrain(doctrine), seed=seed * 2 + 1)
        for n in range(1, 7):
            police.start_sub_game(n)
            thief.start_sub_game(n)
            play_sub_game(police, thief)
            ending = thief.end.ending if thief.end else SURVIVAL
            caught += ending == CAPTURE
            played += 1
    assert caught <= played // 2, (
        f"captured {caught}/{played} against the cage - the grave memory is not "
        f"working. Before it existed this was {played}/{played}."
    )


def test_without_the_memory_the_same_series_is_lost_outright(counted):
    """The control the first version of this file was missing.

    A ratchet test only means something beside the number it is ratcheting
    away from, and that number has to be measured under the same physics on the
    same seeds - not remembered from a comment.
    """
    shared, peer, doctrine = counted
    from dataclasses import replace

    member = population.build(("najamjad-cage",))["najamjad-cage"]
    blind = replace(doctrine, w_grave=0.0)
    caught = played = 0
    for seed in (72000, 72001):
        police = TurnEngine(POLICE, shared, peer, brain=member.make(POLICE), seed=seed * 2)
        thief = TurnEngine(THIEF, shared, peer, brain=ThiefBrain(blind), seed=seed * 2 + 1)
        for n in range(1, 7):
            police.start_sub_game(n)
            thief.start_sub_game(n)
            play_sub_game(police, thief)
            caught += (thief.end.ending if thief.end else SURVIVAL) == CAPTURE
            played += 1
    assert caught == played, (
        f"the cage took only {caught}/{played} from a thief with NO memory - "
        f"then this foil is no longer the evidence this test rests on"
    )
