"""The police's defect was never finding the thief - it was converting.

Mining every sealed log in ``matches/``: 76 police turns began with the thief
one orthogonal step away, and 11 of them ended on its cell. Twenty-seven were
spent placing a barrier - which forfeits the move - from a cell adjacent to the
thief, fifteen standing still, and twenty-three walking somewhere else.

So the order of business is pounce, then everything else. These tests pin the
order, not the tuning: `pounce_floor` decides *when* the evidence is good
enough, and the search owns that number.

Those four counts are what the doctrine of the day *played*; they are not a
verdict on this brain, which did not exist when they were recorded. Replaying
the same 76 states through it - the opponent's served field is not archived but
rebuilds exactly from its trajectory, checked against 2429 of our own - both
pathologies are gone: 27 barriers-instead-of-a-capture became 0 and 15
stand-stills became 0, and conversions went 11 -> 26.

What is left is a lagged fix too thin to bet a whole turn on, and it cannot be
collected by lowering `pounce_floor`, because the pounce *returns*: drop the
floor and `_pursue` stops running, the archive converts nothing extra until
0.10, and the lab's capture rate falls 0.812 -> 0.567. `w_pounce` scores the same evidence as
a term instead, which is the last test below.
"""

from __future__ import annotations

import random

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board, target_of
from p2p_pursuit.domain.brains_base import BrainView
from p2p_pursuit.domain.rules import POLICE
from p2p_pursuit.strategy.params import Doctrine
from p2p_pursuit.strategy.police_brain import PoliceBrain

SIZE = 7
FLAT = [[0.0] * SIZE for _ in range(SIZE)]


def view_for(own, *, board=None, fix=None, lag=0, cells=None, belief_at=None,
             barriers_used=0, step=10, claim_enclosure=True):
    board = board or Board(SIZE)
    belief = BeliefMap(SIZE)
    if belief_at is not None:
        belief = BeliefMap.at(SIZE, belief_at)
    return BrainView(
        role=POLICE, sub_game=1, step=step, own_pos=own, board=board, belief=belief,
        opp_scent=FLAT, own_scent=FLAT, barriers_used=barriers_used, barrier_quota=14,
        steps_remaining=35 - step, survival_threshold=35, trust=0.5,
        map_area="New York", rng=random.Random(0),
        opp_cells=tuple(cells if cells is not None else ([fix] if fix else [])),
        opp_fix=fix, opp_fix_lag=lag, claim_enclosure=claim_enclosure)


def test_it_steps_onto_a_thief_it_has_pinned_exactly():
    """The whole point: an exact fix one step away is a capture, so take it."""
    brain = PoliceBrain(Doctrine())
    view = view_for((3, 3), fix=(3, 4), lag=0)
    decision = brain.decide(view)
    assert decision.barrier is None
    assert target_of((3, 3), decision.move) == (3, 4)


def test_a_capture_beats_a_barrier_even_where_the_barrier_rule_would_also_win():
    """Rule #46 - a barrier onto the thief - is a capture too, and it is worse.

    Rule #21, the truthful answer to a capture claim, is load-bearing for the
    protocol so every peer implements it; rule #46 is not, and several peers we
    have played do not honour it. Same evidence, same trigger: the difference is
    that stepping keeps the move and is answered by a rule that is actually
    agreed, while barring forfeits the move on a rule that may not be.
    """
    brain = PoliceBrain(Doctrine())
    # Belief pinned on the thief's cell, so the old kill-shot branch would fire.
    view = view_for((3, 3), fix=(3, 4), lag=0, belief_at=(3, 4))
    decision = brain.decide(view)
    assert decision.barrier is None, "a barrier here trades a certain capture for a wall"
    assert target_of((3, 3), decision.move) == (3, 4)


def test_it_does_not_pounce_on_a_fix_it_cannot_reach():
    brain = PoliceBrain(Doctrine())
    decision = brain.decide(view_for((0, 0), fix=(6, 6), lag=0))
    assert target_of((0, 0), decision.move) != (6, 6)


def test_a_diffuse_lagged_fix_does_not_trigger_a_pounce_on_its_own():
    """Under `book_v1` the fix is one step old, so five cells share the mass.

    `pounce_floor` is what keeps that from becoming "chase the most likely cell
    every turn", which measured *worse* than not pouncing at all: it bypasses
    the anti-dither tie-break and the cut-off term for a one-in-five shot.
    """
    brain = PoliceBrain(Doctrine())
    spread_out = view_for((3, 2), fix=(3, 4), lag=1,
                          cells=[(3, 4), (2, 4), (4, 4), (3, 3), (3, 5)])
    assert brain._pounce(spread_out) is None


def test_it_refuses_to_wall_off_ground_the_thief_cannot_be_in():
    """287 turns of the archive were spent unable to reach the thief at all.

    Sealing a pocket wins only if the thief is in it. The fix makes that
    checkable, so an empty pocket is now refused even where the two teams agreed
    that enclosure captures.
    """
    brain = PoliceBrain(Doctrine())
    # (0,0) has exits (0,1) and (1,0); barring (1,0) leaves one, barring (0,1)
    # would seal it - with the thief provably at the far corner.
    board = Board(SIZE, {(1, 0)})
    view = view_for((0, 1), board=board, fix=(6, 6), lag=0, claim_enclosure=True)
    assert brain._would_seal(view, (0, 1)) is True


def test_it_still_seals_a_pocket_the_thief_could_be_standing_in():
    brain = PoliceBrain(Doctrine())
    board = Board(SIZE, {(1, 0)})
    view = view_for((0, 1), board=board, fix=(0, 0), lag=0, claim_enclosure=True)
    assert brain._would_seal(view, (0, 1)) is False


def test_it_claims_the_cell_it_lands_on_when_that_cell_is_a_candidate():
    """A missed claim is a missed capture, and the belief threshold missed them.

    The belief peak names the thief's cell about one turn in ten; a fix is
    exact. Claiming does publish our own cell - but the opponent can read that
    off the field we are required to publish anyway, by the same inversion.
    """
    brain = PoliceBrain(Doctrine())
    view = view_for((3, 3), fix=(3, 4), lag=1, cells=[(3, 4), (3, 3)])
    brain.decide(view)
    assert brain.should_claim(view, (3, 4)) is True
    assert brain.should_claim(view, (0, 0)) is False


def test_with_no_fix_it_falls_back_to_the_belief_it_always_used():
    brain = PoliceBrain(Doctrine())
    view = view_for((3, 3), belief_at=(3, 4))
    decision = brain.decide(view)
    assert decision.move in ("N", "S", "E", "W", "STAY")
    assert brain.should_claim(view, (3, 4)) is True


def test_a_declined_chance_still_tilts_the_pursuit():
    """`pounce_floor` gates an early return, so below it a chance was discarded.

    That is the residue the archive replay leaves once the two named
    pathologies are gone: from the same 76 chances today's brain converts 26
    and forfeits none to a barrier or a stand-still, and what it still misses is
    mostly a one-in-five lagged fix that `_pounce` correctly refuses to bet the
    whole turn on. The floor cannot be lowered to collect it - the pounce
    *returns*, so lowering it stops `_pursue` running at all, and the lab's
    capture rate falls 0.812 -> 0.567 while the archive converts nothing extra.
    Priced as a term, the same evidence tilts the move instead of owning it.
    """
    # The thief was here a step ago and could be standing on any of five cells,
    # one of which we are beside. Too thin for the pounce, and without the term
    # the pursuit walks *away* from it to take the middle of the board.
    spread_out = {"fix": (3, 5), "lag": 1,
                  "cells": [(3, 5), (2, 5), (4, 5), (3, 4), (3, 6)]}
    assert PoliceBrain(Doctrine())._pounce(view_for((3, 4), **spread_out)) is None

    off = PoliceBrain(Doctrine(w_pounce=0.0)).decide(view_for((3, 4), **spread_out))
    on = PoliceBrain(Doctrine(w_pounce=1.0)).decide(view_for((3, 4), **spread_out))
    assert target_of((3, 4), off.move) == (2, 4), "not the state this test means"
    assert target_of((3, 4), on.move) == (3, 5)


def test_the_capture_term_is_a_tie_break_and_not_an_override():
    """One unit is one step of ground, which is the whole claim in its units.

    `w_cut` shipped as a raw cell count against a distance in steps and the
    mismatch decided the league - a cell of territory outscoring a step of
    pursuit twelve times over. So this term is pinned to the scale it is
    supposed to trade against: a cell that *certainly* holds the thief is worth
    one step, and no amount of probability may outrank a genuinely closer cell.
    """
    board = Board(SIZE)
    # The fix is far away and lagged; the pursuit target is right beside us.
    view = view_for((3, 3), board=board, fix=(6, 6), lag=1,
                    cells=[(6, 6), (5, 6), (6, 5)], belief_at=(3, 4))
    chosen = PoliceBrain(Doctrine(w_pounce=1.0)).decide(view)
    assert chosen.barrier is None
    assert target_of((3, 3), chosen.move) == (3, 4), "a distant maybe outranked a near certainty"


def test_the_capture_term_does_nothing_under_a_lag_zero_physics():
    """Under `subtractive_chebyshev_v1` the fix is current, so `_where` is a delta.

    Either the pounce can reach that one cell and has already spent the turn on
    it, or it cannot and every cell this scores carries no mass at all. Measured
    over 640 lab sub-games the two settings are identical to three decimals, so
    the term carries no risk into the physics we prefer to negotiate.
    """
    same = {"fix": (3, 6), "lag": 0, "cells": [(3, 6)]}
    off = PoliceBrain(Doctrine(w_pounce=0.0)).decide(view_for((3, 3), **same))
    on = PoliceBrain(Doctrine(w_pounce=4.0)).decide(view_for((3, 3), **same))
    assert off.move == on.move
