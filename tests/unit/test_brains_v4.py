"""v4 doctrine regressions: each of these encodes a measured defect of v3.

Every test here corresponds to a bug found by instrumenting real games, so a
future refactor that silently reintroduces one fails loudly rather than only
showing up as a slightly worse capture rate months later.
"""

from __future__ import annotations

import random

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.brains_base import BrainView
from p2p_pursuit.strategy.police_brain import PoliceBrain
from p2p_pursuit.strategy.thief_brain import ThiefBrain

SIZE = 7


def make_view(role, own_pos, *, belief_at=None, opp_scent=None, step=5,
              barriers=(), barriers_used=0, flat=False):
    board = Board(SIZE, set(barriers))
    belief = BeliefMap.at(SIZE, belief_at or (3, 3))
    if flat:  # uniform posterior - no cell testifies
        n = SIZE * SIZE
        belief.grid = [[1.0 / n] * SIZE for _ in range(SIZE)]
    zeros = [[0.0] * SIZE for _ in range(SIZE)]
    return BrainView(
        role=role, sub_game=1, step=step, own_pos=own_pos, board=board, belief=belief,
        opp_scent=opp_scent or zeros, own_scent=zeros, barriers_used=barriers_used,
        barrier_quota=14, steps_remaining=30, survival_threshold=35, trust=0.5,
        map_area="", rng=random.Random(7))


def trail(cells: list[tuple[int, int]], value=0.9):
    """A scent field whose freshest cell is `cells[-1]`."""
    field = [[0.0] * SIZE for _ in range(SIZE)]
    for i, (r, c) in enumerate(cells):
        field[r][c] = value - 0.05 * (len(cells) - 1 - i)
    return field


# -- police -------------------------------------------------------------------
def test_police_ambushes_the_peak_once_then_stops_idling_on_it():
    """21% of all police turns were idle STAY: standing on the argmax scored
    distance 0, so nothing could beat it and the police froze for the game.

    The pathology is *idling*, not the STAY token. A barrier placement forfeits
    the move by rule, so a placement also reports ``move="STAY"`` - and a police
    spending its turn to close a door is doing the opposite of freezing. The v6
    doctrine places barriers here, which is what surfaced the distinction.
    """
    brain = PoliceBrain()
    own = (3, 3)
    first = brain.decide(make_view("police", own, belief_at=own))
    second = brain.decide(make_view("police", own, belief_at=own, step=6))
    third = brain.decide(make_view("police", own, belief_at=own, step=7))
    assert first.move == "STAY", "one ambush turn on the peak is worth having"
    for turn, decision in (("second", second), ("third", third)):
        assert not (decision.move == "STAY" and decision.barrier is None), \
            f"a {turn} consecutive idle turn on the peak is the pathology"

    # The original assertion, kept exactly, for the case where no placement is
    # possible - then an idle STAY is the only way to score a STAY at all.
    spent = PoliceBrain()
    kwargs = {"belief_at": own, "barriers_used": 14}
    assert spent.decide(make_view("police", own, **kwargs)).move == "STAY"
    assert spent.decide(make_view("police", own, step=6, **kwargs)).move != "STAY"
    assert spent.decide(make_view("police", own, step=7, **kwargs)).move != "STAY"


def test_police_retargets_onto_the_cloud_not_across_the_board():
    """Retargeting to the globally second-best cell abandoned the probability
    cloud and measurably cost captures; the step must stay adjacent."""
    brain = PoliceBrain()
    own = (3, 3)
    brain.decide(make_view("police", own, belief_at=own))          # ambush turn
    target = brain._next_best_cell(make_view("police", own, belief_at=own))
    assert target in list(Board(SIZE, set()).neighbors4(own))


def test_police_breaks_ties_against_reversing():
    """28% of real moves were A->B->A step-backs as the belief peak jittered."""
    brain = PoliceBrain()
    brain._last_move = "E"
    view = make_view("police", (3, 3), flat=True)
    # On a flat posterior every direction ties on distance, so the reversal
    # penalty is the only thing that decides - it must not pick "W".
    assert brain._pursue(view, (3, 3)).move != "W"


def test_kill_shot_can_actually_fire():
    """v3's kill shot needed belief 0.30 while the measured posterior peak never
    exceeded 0.294 - the barrier-capture rule (#46) was unreachable dead code."""
    brain = PoliceBrain()
    own, adjacent = (3, 3), (3, 4)
    view = make_view("police", own, belief_at=adjacent)
    decision = brain.decide(view)
    assert decision.barrier == list(adjacent) or tuple(decision.barrier or ()) == adjacent
    assert decision.move == "STAY", "a placement forfeits the move"


def test_rolling_window_forgets_the_opening_certainty():
    """The belief starts as a delta (b_max = 1.0) on the known start cell. An
    all-time-max reference pins the threshold at 0.85 forever and reproduces
    exactly the dead-threshold bug it was meant to replace."""
    brain = PoliceBrain()
    brain._barrier_play(make_view("police", (0, 0), belief_at=(0, 0)), (0, 0), 1.0)
    for _ in range(20):  # a long fog-of-war stretch with a flat posterior
        brain._barrier_play(make_view("police", (0, 0), flat=True), (6, 6), 0.02)
    assert max(brain._recent) < 0.5, "the opening delta must age out of the window"


# -- thief --------------------------------------------------------------------
def test_thief_projects_from_the_pursuer_trail_not_the_belief_peak():
    """v3 taught the police that the belief peak jitters and the scent trail
    does not, then left the thief using the peak."""
    brain = ThiefBrain()
    view_a = make_view("thief", (6, 6), opp_scent=trail([(0, 0), (0, 1)]))
    brain._track_trail(view_a)
    view_b = make_view("thief", (6, 6), opp_scent=trail([(0, 1), (0, 2)]), step=6)
    brain._track_trail(view_b)
    # trail moved (0,1)->(0,2): heading east, so the projection leads east of it
    assert brain._project(view_b, (5, 5)) == (0, 4)


def test_thief_chase_test_is_barrier_aware():
    """Manhattan under-estimates around barriers, so the thief juked while the
    pursuer was walled off - and juking costs escape speed."""
    brain = ThiefBrain()
    wall = [(2, c) for c in range(SIZE)]  # a full wall between rows 1 and 3
    view = make_view("thief", (3, 3), barriers=wall)
    manhattan = abs(1 - 3) + abs(3 - 3)
    assert brain._pursuer_distance(view, (1, 3)) > manhattan


def test_thief_keeps_corner_discipline_in_the_second_half():
    """Corner discipline used to switch off at half-time - precisely when a
    police holding an unspent quota can seal a pocket."""
    brain = ThiefBrain()
    late = make_view("thief", (3, 3), step=30)
    corner_ward = brain._pick_move(late).move
    # from the centre, a late thief must not choose to walk to the board edge
    assert corner_ward in ("N", "S", "E", "W", "STAY")
    edge_view = make_view("thief", (0, 3), step=30)
    assert brain._pick_move(edge_view).move != "STAY", "do not linger on an edge"


def test_thief_never_stays_twice_in_a_row():
    """STRATEGY.md always claimed this; only a soft penalty was implemented."""
    brain = ThiefBrain()
    brain._last_move = "STAY"
    assert brain._pick_move(make_view("thief", (3, 3))).move != "STAY"


def test_thief_lie_is_not_a_deterministic_function_of_public_data():
    """We transmit the scent field, so an opponent can recompute any
    deterministic function of it - the old lie picked the single furthest stale
    cell, which made the lie derivable from public data."""
    scent = [[0.0] * SIZE for _ in range(SIZE)]
    for cell in [(0, 0), (0, 6), (6, 0), (6, 6)]:  # equidistant stale candidates
        scent[cell[0]][cell[1]] = 0.4
    regions = set()
    for seed in range(40):
        brain = ThiefBrain()
        view = make_view("thief", (3, 3))
        view = BrainView(**{**view.__dict__, "own_scent": scent,
                            "rng": random.Random(seed)})
        region, intent = brain.hint_plan(view, None)
        if intent == "lie":
            regions.add(region)
    assert len(regions) > 1, "a single region every time is a decodable lie"


# -- v5: claiming an enclosure ------------------------------------------------
def test_police_claims_an_enclosed_thief():
    """Book 3.4: a thief with no legal move is captured. A foreign peer never
    confesses it - we squeezed the reference peer into a corner in a live match,
    sealed both exits, and still lost to "survival" 23 turns later."""
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    shared = make_shared()
    engine = TurnEngine("police", shared, make_peer("police"), seed=1)
    corner = (shared.grid_size - 1, shared.grid_size - 1)
    for cell in [(corner[0] - 1, corner[1]), (corner[0], corner[1] - 1)]:
        engine.board.add_barrier(cell)
    scent = [[0.0] * shared.grid_size for _ in range(shared.grid_size)]
    scent[corner[0]][corner[1]] = 0.9          # their trail names the corner
    engine.opp_public.append({"kind": "step", "scent": scent})
    engine.opp_hashes.append("x")

    package = engine.build_own_step()
    assert "event" in package, "an enclosed thief must be claimed, not chased"
    assert engine.end is not None
    assert engine.end.ending == "capture"
    assert engine.end.winner == "police"
    assert "enclosed" in engine.end.cause


def test_enclosure_claim_can_be_switched_off_for_an_opponent_that_rejects_it():
    """Measured live against the unmodified reference peer (2026-08-01): we
    enclosed their thief at (6,6) and claimed it, they kept playing, never sent
    their audit package, and sub-game 2 died on `both peers claim role thief`.
    The rule is real (book 3.4) but it is a per-opponent agreement, so it has to
    be switchable - and the switch must actually reach the engine.
    """
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    shared = make_shared()
    engine = TurnEngine("police", shared, make_peer("police", claim_enclosure=False), seed=1)
    corner = (shared.grid_size - 1, shared.grid_size - 1)
    for cell in [(corner[0] - 1, corner[1]), (corner[0], corner[1] - 1)]:
        engine.board.add_barrier(cell)
    scent = [[0.0] * shared.grid_size for _ in range(shared.grid_size)]
    scent[corner[0]][corner[1]] = 0.9
    engine.opp_public.append({"kind": "step", "scent": scent})
    engine.opp_hashes.append("x")

    package = engine.build_own_step()
    assert "commit" in package, "with the claim off we must play on, not claim"
    assert engine.end is None


def test_police_does_not_claim_on_a_stale_trail():
    """A claim we cannot substantiate is worse than a missed capture."""
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    shared = make_shared()
    engine = TurnEngine("police", shared, make_peer("police"), seed=1)
    corner = (shared.grid_size - 1, shared.grid_size - 1)
    for cell in [(corner[0] - 1, corner[1]), (corner[0], corner[1] - 1)]:
        engine.board.add_barrier(cell)
    scent = [[0.0] * shared.grid_size for _ in range(shared.grid_size)]
    scent[corner[0]][corner[1]] = 0.3          # too decayed to name a cell
    engine.opp_public.append({"kind": "step", "scent": scent})
    engine.opp_hashes.append("x")

    package = engine.build_own_step()
    assert "commit" in package, "an unsubstantiated enclosure must not be claimed"
    assert engine.end is None


def test_the_squeeze_stops_one_door_short_when_enclosure_is_not_agreed():
    """Measured live 2026-08-01 against the reference peer: we barred (6,5) and
    (5,6), their thief sat in (6,6) for 27 turns, and our police finished at
    (6,4) - outside the wall it had built. Survival, 5 points where 20 was on
    offer. Sealing the last door only wins if the opponent honours book 3.4.
    """
    from p2p_pursuit.strategy.squeeze import squeeze_play

    board = Board(SIZE, {(6, 5)})          # corner (6,6) already down to one exit
    corner, beside = (6, 6), (5, 6)
    assert squeeze_play(board, beside, corner, quota_left=10, reserve=2,
                        claim_enclosure=True) == beside, "with the rule agreed, seal it"
    assert squeeze_play(board, beside, corner, quota_left=10, reserve=2,
                        claim_enclosure=False) is None, "without it, leave the door open"


def test_the_view_carries_the_negotiated_enclosure_rule():
    """The flag is useless if it stops at the config: the brain decides on the
    view, so the view is what has to know."""
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    engine = TurnEngine("police", make_shared(), make_peer("police", claim_enclosure=False))
    assert engine._view().claim_enclosure is False
    assert make_view("police", (3, 3)).claim_enclosure is True, "default stays our doctrine"
