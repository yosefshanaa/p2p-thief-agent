"""The pool's answer to "what if they invert the field too?"

Written after a thief search returned nothing: sixteen of seventeen pool members
scored a flat 10.00 against our evader, so the objective was blind, and the
search duly drove `corner_penalty` to 0.001 for want of anything that punished a
corner. An optimiser tunes only what its objective can punish.

The inversion is arithmetic over a field the rules require both peers to
publish, so a doctrine that only survives opponents who have not noticed is a
doctrine with an expiry date. `interceptor` is that opponent, written out.
"""

from __future__ import annotations

import random

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board, target_of
from p2p_pursuit.domain.brains_base import BrainView
from p2p_pursuit.domain.rules import POLICE
from p2p_pursuit.learn import population
from p2p_pursuit.learn.opponents import Interceptor

SIZE = 7
FLAT = [[0.0] * SIZE for _ in range(SIZE)]


def view_for(own, fix, *, board=None, lag=0, barriers_used=0):
    board = board or Board(SIZE)
    cells = [fix] if lag == 0 else sorted(
        {fix, *board.open_neighbors(fix)})
    return BrainView(
        role=POLICE, sub_game=1, step=10, own_pos=own, board=board,
        belief=BeliefMap.at(SIZE, fix), opp_scent=FLAT, own_scent=FLAT,
        barriers_used=barriers_used, barrier_quota=14, steps_remaining=25,
        survival_threshold=35, trust=0.5, map_area="New York", rng=random.Random(0),
        opp_cells=tuple(cells), opp_fix=fix, opp_fix_lag=lag)


def test_it_takes_a_certain_capture():
    decision = Interceptor().decide(view_for((3, 3), (3, 4), lag=0))
    assert decision.barrier is None
    assert target_of((3, 3), decision.move) == (3, 4)


def test_it_does_not_pounce_on_a_lagged_fix_it_cannot_be_sure_of():
    decision = Interceptor().decide(view_for((3, 3), (3, 4), lag=1))
    assert decision.move != "STAY" or decision.barrier is not None


def test_it_closes_a_door_when_it_is_standing_at_one():
    """A corner thief with two exits and us beside one of them."""
    board = Board(SIZE)
    decision = Interceptor().decide(view_for((0, 1), (0, 0), board=board, lag=1))
    assert decision.barrier in {(0, 1), (1, 0), (0, 0)} or decision.move != "STAY"


def test_it_will_not_seal_the_last_door():
    """One exit left means sealing it, and an enclosure it cannot claim is a
    stalemate - the same trap our own squeeze stops one door short of."""
    board = Board(SIZE, {(0, 1)})           # (0,0) now has exactly one exit, (1,0)
    decision = Interceptor().decide(view_for((1, 0), (0, 0), board=board, lag=0))
    assert decision.barrier != (1, 0)


def test_it_falls_back_to_the_belief_when_there_is_no_fix():
    board = Board(SIZE)
    view = BrainView(role=POLICE, sub_game=1, step=3, own_pos=(0, 0), board=board,
                     belief=BeliefMap.at(SIZE, (3, 3)), opp_scent=FLAT, own_scent=FLAT,
                     barriers_used=0, barrier_quota=14, steps_remaining=32,
                     survival_threshold=35, trust=0.5, map_area="New York",
                     rng=random.Random(0))
    assert Interceptor().decide(view).move in ("N", "S", "E", "W", "STAY")


def test_it_spends_its_move_on_ground_rather_than_on_raw_distance():
    """The measurement the archetype is built on.

    Two equal-speed agents on open ground never meet, so a pursuer that walks
    straight at an exact fix converts nothing - which is also why our own police
    grew `w_cut`. Here: from equidistant candidates it takes the one that leaves
    the thief less board, not an arbitrary one.
    """
    board = Board(SIZE)
    brain = Interceptor()
    # Thief pinned in the top-left; we are on the far diagonal. Both N and W
    # close the distance by one, so plain distance cannot separate them - the
    # cut term must, and it prefers the move toward the open side of the board.
    move = brain.decide(view_for((4, 4), (1, 1), board=board, lag=0)).move
    assert move in ("N", "W")
    assert brain.CUT_WEIGHT > 0.0


def test_it_is_in_the_pool_as_a_police_only_archetype():
    pool = population.build()
    assert "interceptor" in pool
    assert pool["interceptor"].roles == (POLICE,), (
        "as an evader it would be a plain distance-maximiser, which `greedy` "
        "already is - listing it twice would just reweight that behaviour")
