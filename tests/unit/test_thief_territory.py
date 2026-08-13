"""The thief must see a pocket as a pocket, not as a cell with exits.

Measured vs orcai-mj on 2026-08-12/13: our thief was captured at (5,6) or (6,6)
in nine consecutive thief sub-games, across two doctrines and three seeds. Their
police herds it into the right-edge pocket and then spends barriers - by sealing
the mouth (`enclosed`) or by dropping one onto the cell (`barrier onto (5,6)`).

`w_mobility` counts open neighbours and `w_mobility2` averages their openness, so
both score that pocket as roomy until the turn it closes. `w_territory` counts
the cells we reach *before the pursuer*, which is the quantity that actually
collapses as we are herded, and `w_trap` turns the collapse into a gradient the
thief can climb out of - but only while the pursuer still has quota to seal with.
"""

from __future__ import annotations

from p2p_pursuit.domain.board import Board
from p2p_pursuit.strategy.params import Doctrine
from p2p_pursuit.strategy.pathing import bfs_distances
from p2p_pursuit.strategy.thief_brain import ThiefBrain

SIZE = 7
UNREACHABLE = SIZE * SIZE


def owned(board: Board, mine: tuple[int, int], pursuer: tuple[int, int]) -> int:
    return ThiefBrain._territory(bfs_distances(board, mine),
                                 bfs_distances(board, pursuer), UNREACHABLE)


def test_the_pocket_that_killed_us_scores_far_smaller_than_the_open_board():
    """(5,6) with the real cage vs (3,3) in the open, same pursuer distance."""
    cage = Board(SIZE, {(5, 5), (4, 6)})        # the barriers they actually placed
    pocket = owned(cage, (5, 6), (6, 5))

    open_board = Board(SIZE, set())
    middle = owned(open_board, (3, 3), (3, 1))

    assert pocket < middle / 2, (
        f"a two-cell pocket ({pocket}) must not look comparable to the open "
        f"board ({middle}) - that is precisely the blindness that lost nine "
        f"sub-games")


def test_openness_ties_where_territory_separates():
    """Why a new term was needed rather than a bigger weight on the old ones.

    By the final cell openness has collapsed too - but by then the thief is
    already dead. The decision that kills it happens earlier, among cells whose
    door count is identical and whose ownership is not.
    """
    cage = Board(SIZE, {(5, 5), (4, 6)})
    doomed, safe = (6, 6), (0, 0)
    open_board = Board(SIZE, set())

    assert len(cage.open_neighbors(doomed)) == len(open_board.open_neighbors(safe)) == 2, (
        "both cells have exactly two doors: openness cannot rank them")

    trapped = owned(cage, doomed, (6, 5))          # pursuer at the mouth
    roomy = owned(open_board, safe, (6, 6))        # pursuer across the board

    assert trapped < roomy / 3, (
        f"territory must separate what openness ties: {trapped} owned in the "
        f"pocket vs {roomy} in the open")


def test_ties_go_to_the_pursuer():
    """Arriving together is arriving into it, so an equidistant cell is not ours."""
    board = Board(SIZE, set())
    mine = bfs_distances(board, (3, 3))
    theirs = bfs_distances(board, (3, 3))       # same cell: nothing is ours
    assert ThiefBrain._territory(mine, theirs, UNREACHABLE) == 0


def test_cells_the_pursuer_cannot_reach_stay_ours():
    """A walled-off pursuer owns nothing, however close it stands."""
    board = Board(SIZE, {(0, 1), (1, 0), (1, 1)})   # pursuer sealed into (0,0)
    assert owned(board, (3, 3), (0, 0)) > 30


def test_the_thief_walks_out_of_the_pocket_rather_than_deeper_in():
    """End to end: given the killing board, the chosen move must not stay in."""
    import random
    from types import SimpleNamespace

    from p2p_pursuit.domain.belief import BeliefMap

    board = Board(SIZE, {(5, 5), (4, 6)})
    belief = BeliefMap(SIZE)
    belief.grid[6][5] = 1.0                      # pursuer where it actually stood
    flat = [[0.0] * SIZE for _ in range(SIZE)]
    view = SimpleNamespace(
        board=board, own_pos=(5, 6), belief=belief, own_scent=flat,
        opp_scent=flat, step=12, sub_game=1, survival_threshold=35,
        barrier_quota=14, rng=random.Random(0))

    brain = ThiefBrain(Doctrine())
    decision = brain._pick_move(view)

    assert decision.move in ("N", "S", "W", "E", "STAY")
    # (5,6) exits: N=(4,6) barred, W=(5,5) barred, S=(6,6) deeper in, E off-board.
    # Every legal move is bad; the point is that it does not choose to sit still
    # and let the mouth close, which is what the logs show it doing.
    assert decision.move != "STAY", "camping in a closing pocket is how it died"
