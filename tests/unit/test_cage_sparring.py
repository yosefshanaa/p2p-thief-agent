"""The opponent the thief objective could not see.

`evader` was added because every sparring thief read the belief rather than
inverting the field, so the police search met nobody who could hold a gap and
duly certified a doctrine that converted 0 of 6 on the wire. The thief half of
the pool has the mirror-image hole, and the archive names it: of the eight
counted sub-games in which our thief was captured, four say ``barrier onto ...``
or ``enclosed``, and all eight end on the outer ring or one step off it. Nobody
in the pool could produce that. `BarrierHappy` walls the thief's own cell when
the belief peak happens to sit next door, which is a kill shot a competent
evader never offers - our thief survives it 100% under subtractive.

So the measured objective said 98.4% survival, 20 of 22 police archetypes never
scoring at all, while the two teams playing this physics took our thief in two
of three. `Cager` closes that: it inverts the field like a real opponent, and it
optimises the thief's escape room rather than the distance to it.

Two orderings of the same idea are kept, because they are not the same opponent:

* ``cager`` closes the gap and lets room break the ties. Our shipped thief
  survives it 40 in 40 under subtractive.
* ``constrictor`` leads with room, so it will decline a step that hands the
  thief a tie and walk it into the wall rather than at it. Our shipped thief
  loses to it 40 in 40 - on the same physics, the same doctrine, the same seeds.

That second number is the point of this file. It is the live loss reproduced
offline for the first time, and no weight in the vector moves it: sweeping
`w_trap`, `trap_floor`, `w_mobility2`, `w_safe2` across their whole searched
range, and `w_strike` to 1000, leaves it at 0 of 40. `evader` survives the same
opponent 40 in 40, so the gap is a policy our thief does not have rather than a
weight it has not found.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.domain.scent import SUBTRACTIVE_V1
from p2p_pursuit.domain.scoring import CAPTURE
from p2p_pursuit.learn import arena
from p2p_pursuit.learn.arena import default_shared, sub_game
from p2p_pursuit.learn.opponents import Cager
from p2p_pursuit.learn.population import BUILTIN, build
from p2p_pursuit.strategy.params import active
from p2p_pursuit.strategy.thief_brain import ThiefBrain

#: The physics the two teams that beat our thief actually served, and the
#: doctrine we played against them. Both are named rather than inherited: the
#: effect is a lag-0 model handing the pursuer an exact fix, and it is invisible
#: under book_v1, where the same fix arrives a step stale.
DOCTRINE = Path("config/doctrine-subtractive.json")
SEEDS = tuple(range(4000, 4040))


@pytest.fixture
def subtractive(monkeypatch):
    monkeypatch.setattr(arena, "QUIET",
                        dataclasses.replace(arena.QUIET, scent_model=SUBTRACTIVE_V1))
    return active(DOCTRINE)


def _survival(thief, police_name: str) -> float:
    """Fraction of the seed sequence this thief lives through."""
    member = BUILTIN[police_name]
    lived = 0
    for index, seed in enumerate(SEEDS):
        ending, _, _ = sub_game(default_shared(), member.make(POLICE), thief(),
                                seed, always_claim=bool(index % 2))
        lived += ending != CAPTURE
    return lived / len(SEEDS)


def test_the_pool_offers_a_police_our_thief_cannot_survive(subtractive):
    """The hole the archive says exists, now visible to the objective.

    Not a claim that losing is correct - a claim that the lab can finally see
    the way we lose. Before `constrictor` the worst any pool police managed
    against this doctrine was our own police at 65%, and every published
    opponent sat at 100%.
    """
    assert _survival(lambda: ThiefBrain(subtractive), "constrictor") == 0.0


def test_the_cage_is_beatable_so_the_objective_has_somewhere_to_go(subtractive):
    """An opponent nobody can beat teaches a search nothing.

    `evader` is 30 lines and holds one rule our thief does not: never end the
    move inside the pursuer's one-step reach. It survives the same opponent on
    the same seeds, so the 0% above is a reachable policy gap.
    """
    assert _survival(lambda: BUILTIN["evader"].make(THIEF), "constrictor") == 1.0


def test_closing_the_gap_and_taking_the_room_are_different_opponents(subtractive):
    """Both orderings are kept because our thief's record against them differs.

    If they scored alike there would be no reason to pay for two pool members.
    """
    ours_ = lambda: ThiefBrain(subtractive)  # noqa: E731
    assert _survival(ours_, "cager") == 1.0
    assert _survival(ours_, "constrictor") == 0.0


def test_the_cager_never_spends_a_turn_walling_its_own_cell(subtractive):
    """The first version of this brain did, and stood still for a whole sub-game.

    A barrier on the cell you occupy is legal by the letter of the rules and
    forfeits the move for nothing; `safe_decision` rejected the placement and
    substituted a bare STAY, so the cage sat on its start cell for 35 steps and
    reported a survival it had never contested. Both halves are asserted - that
    no placement targets the cell we stand on, and that the pursuer actually
    goes somewhere - because the first failed silently and only the second was
    visible in the score.
    """
    seen: list[tuple] = []
    original = Cager._decide_move

    def watched(self, view):
        decision = original(self, view)
        seen.append((view.own_pos, decision.barrier))
        return decision

    Cager._decide_move = watched
    try:
        for index, seed in enumerate(SEEDS[:8]):
            sub_game(default_shared(), BUILTIN["cager"].make(POLICE),
                     ThiefBrain(subtractive), seed, always_claim=bool(index % 2))
    finally:
        Cager._decide_move = original

    assert seen, "the cager never decided anything"
    assert not [own for own, barrier in seen if barrier == own]
    assert len({own for own, _ in seen}) > 1, "the cage never left its start cell"


@pytest.mark.parametrize("name", ["cager", "constrictor"])
def test_the_cage_is_registered_for_the_police_seat_only(name: str):
    """A thief cannot place a barrier, so a cage in the thief seat is a no-op."""
    assert build((name,))[name].roles == (POLICE,)
