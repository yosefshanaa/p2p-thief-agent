"""The thief's defect: it walked into the pursuer's reach, 43 times.

Across 35 archived thief sub-games our thief finished its move inside the cells
the pursuer could take next on 43 turns, and was captured on 14 of them. Both
losses to gal-roy1 are the same picture - it stepped to a cell orthogonally
adjacent to a pursuer whose exact cell its own scent feed was carrying, and the
pursuer stepped on it or barred it.

Distance and the claim-radius risk term both treat the pursuer as a cloud. This
is the term that treats it as an agent with a move left to play.
"""

from __future__ import annotations

import random

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board, target_of
from p2p_pursuit.domain.brains_base import BrainView
from p2p_pursuit.domain.rules import THIEF
from p2p_pursuit.strategy.params import Doctrine
from p2p_pursuit.strategy.thief_brain import ThiefBrain

SIZE = 7
FLAT = [[0.0] * SIZE for _ in range(SIZE)]


def view_for(own, *, board=None, fix=None, lag=0, cells=None, barriers_used=0,
             step=10, claim_enclosure=True):
    board = board or Board(SIZE)
    return BrainView(
        role=THIEF, sub_game=1, step=step, own_pos=own, board=board,
        belief=BeliefMap.at(SIZE, fix) if fix else BeliefMap(SIZE),
        opp_scent=FLAT, own_scent=FLAT, barriers_used=barriers_used, barrier_quota=14,
        steps_remaining=35 - step, survival_threshold=35, trust=0.5,
        map_area="New York", rng=random.Random(0),
        opp_cells=tuple(cells if cells is not None else ([fix] if fix else [])),
        opp_fix=fix, opp_fix_lag=lag, claim_enclosure=claim_enclosure)


def test_it_will_not_step_into_the_cells_the_pursuer_can_take_next():
    """The gal-roy1 losses, in one assertion."""
    brain = ThiefBrain(Doctrine())
    # Open board, pursuer pinned two steps east. Of our five moves exactly one -
    # E, onto (3,4) - is inside its reach, and four are not, so the choice is
    # unforced and the term is the only thing that can decide it.
    view = view_for((3, 3), fix=(3, 5), lag=0)
    landing = target_of((3, 3), brain.decide(view).move)
    reach = {(3, 5), *Board(SIZE).open_neighbors((3, 5))}
    assert landing not in reach, f"stepped to {landing}, inside the pursuer's reach"
    assert landing != (3, 4)


def test_the_strike_map_is_the_pursuers_reach_not_its_cell():
    brain = ThiefBrain(Doctrine())
    view = view_for((0, 0), fix=(3, 3), lag=0)
    strike = brain._danger(view)
    assert strike[(3, 3)] == 1.0
    for cell in Board(SIZE).open_neighbors((3, 3)):
        assert strike[cell] == 1.0, "every cell it can step to is equally lethal"
    assert strike.get((3, 5), 0.0) == 0.0, "two steps away is not its next move"


def test_a_lagged_fix_spreads_the_danger_instead_of_pinning_it():
    brain = ThiefBrain(Doctrine())
    pinned = brain._danger(view_for((0, 0), fix=(3, 3), lag=0))
    lagged = brain._danger(view_for((0, 0), fix=(3, 3), lag=1))
    assert len(lagged) > len(pinned), "a step of uncertainty widens the zone"
    assert max(lagged.values()) <= 1.0 + 1e-9
    # The rim is where the dilution shows. The middle stays at 1.0 and should:
    # wherever the pursuer went, it can come back, so that cell is still its to
    # take. Cells only one of its five options can reach are not.
    assert lagged[(3, 3)] == 1.0
    assert 0.0 < lagged[(1, 3)] < 0.5, "reachable from one branch only"


def test_the_seal_term_reads_the_negotiated_enclosure_rule_both_ways():
    """A pocket is a death trap or a fortress depending on what was agreed.

    Where enclosure captures, a cell whose every exit the pursuer can bar is
    lethal. Where it does not, being sealed in is a *survival* - it is how the
    reference peer beat us on 2026-08-01, sitting in a pocket for 27 turns while
    our police finished outside its own wall.
    """
    brain = ThiefBrain(Doctrine())
    board = Board(SIZE, {(5, 5), (4, 6)})       # the cage they actually built
    agreed = view_for((5, 6), board=board, fix=(6, 5), lag=0, claim_enclosure=True)
    brain._strike = brain._danger(agreed)
    trapped = brain._danger_at(agreed, (5, 6), threat=0.8)

    unagreed = view_for((5, 6), board=board, fix=(6, 5), lag=0, claim_enclosure=False)
    brain._strike = brain._danger(unagreed)
    fortress = brain._danger_at(unagreed, (5, 6), threat=0.8)

    assert trapped > fortress, (
        "the same geometry cannot carry the same penalty under both rulesets")
    assert fortress == 0.0, "unagreed, a sealed pocket is not a danger at all"


def test_with_no_fix_nothing_changes()  :
    """Every new term must vanish cleanly when the field cannot be inverted."""
    brain = ThiefBrain(Doctrine())
    view = view_for((3, 3))
    assert brain._danger(view) == {}
    assert brain.decide(view).move in ("N", "S", "E", "W", "STAY")


def test_it_still_prefers_room_when_every_cell_is_out_of_reach():
    """The strike term must not flatten the doctrine where it does not apply."""
    brain = ThiefBrain(Doctrine())
    view = view_for((3, 3), fix=(0, 0), lag=0)
    move = brain.decide(view).move
    assert move != "STAY", "re-emitting on one cell is never the answer in the open"
