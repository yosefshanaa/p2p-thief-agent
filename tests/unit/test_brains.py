"""Brain doctrine: legality invariant, kill shot, self-trap veto, plugin loading."""

import random

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.brains_base import BrainBase, BrainView, load_brain
from p2p_pursuit.domain.rules import POLICE, THIEF, validate
from p2p_pursuit.strategy.pathing import bfs_distances, still_connected
from p2p_pursuit.strategy.police_brain import PoliceBrain
from p2p_pursuit.strategy.thief_brain import ThiefBrain


def view_for(role, pos, board=None, belief=None, seed=0, **kw):
    board = board or Board(7)
    belief = belief or BeliefMap(7)
    defaults = {"role": role, "sub_game": 1, "step": 1, "own_pos": pos, "board": board,
                "belief": belief, "opp_scent": [[0.0] * 7 for _ in range(7)],
                "own_scent": [[0.0] * 7 for _ in range(7)], "barriers_used": 0,
                "barrier_quota": 14, "steps_remaining": 30, "survival_threshold": 35,
                "trust": 0.5, "map_area": "", "rng": random.Random(seed)}
    defaults.update(kw)
    return BrainView(**defaults)


def test_pathing_and_connectivity():
    b = Board(7)
    b.add_barrier((1, 0))
    d = bfs_distances(b, (0, 0))
    assert d[(2, 0)] == 4  # around the barrier: (0,1)(1,1)(2,1)(2,0)
    assert still_connected(b, (0, 2), (0, 0), (5, 5))
    b2 = Board(3, {(0, 1), (1, 1)})
    assert not still_connected(b2, (2, 1), (0, 0), (2, 2))  # would wall us off


def test_police_kill_shot_on_near_certain_adjacent_cell():
    belief = BeliefMap.at(7, (3, 4))
    decision = PoliceBrain()._decide_move(view_for(POLICE, (3, 3), belief=belief))
    assert decision.barrier == (3, 4) and decision.move == "STAY"


def test_police_pursues_belief_argmax():
    belief = BeliefMap.at(7, (6, 6))
    decision = PoliceBrain()._decide_move(view_for(POLICE, (0, 0), belief=belief))
    assert decision.move in {"S", "E"}


def test_thief_flees_the_belief_cloud():
    belief = BeliefMap.at(7, (0, 0))  # police believed at the NW corner
    decision = ThiefBrain()._pick_move(view_for(THIEF, (3, 3), belief=belief))
    assert decision.move in {"S", "E"}


def test_brains_always_legal_under_random_boards():
    rng = random.Random(9)
    for trial in range(60):
        board = Board(7)
        for _ in range(rng.randrange(0, 10)):
            board.add_barrier((rng.randrange(7), rng.randrange(7)))
        pos = next(((r, c) for r in range(7) for c in range(7)
                    if board.is_open((r, c))), None)
        for role, brain in ((POLICE, PoliceBrain()), (THIEF, ThiefBrain())):
            view = view_for(role, pos, board=board, belief=BeliefMap(7), seed=trial)
            decision = brain.decide(view)
            assert validate(board, role, pos, decision, 0, 14) is None, (role, decision)


def test_load_brain_default_and_custom():
    assert isinstance(load_brain(None, POLICE), PoliceBrain)
    assert isinstance(load_brain(None, THIEF), ThiefBrain)
    custom = load_brain("p2p_pursuit.strategy.thief_brain:ThiefBrain", THIEF)
    assert isinstance(custom, BrainBase)


def test_hint_plans_return_region_and_intent():
    for role, brain in ((POLICE, PoliceBrain()), (THIEF, ThiefBrain())):
        view = view_for(role, (3, 3))
        region, intent = brain.hint_plan(view, brain.decide(view))
        assert isinstance(region, str) and intent in {"truth", "lie"}
