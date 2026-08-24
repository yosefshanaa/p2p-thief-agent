"""Whether to spend a wall, and where to put it - as a mixin.

Split out of :mod:`.police_brain` (§3.2, mixin strategy ch. 4.2). One concern:
the barrier. A placement forfeits the move, is permanent, and comes out of a
quota of 14, so each question here is whether a wall pays for itself - does it
seal the thief's region, is the target already cornered, and which adjacent
cell takes the most ground away. Choosing to pursue instead stays in
:class:`~.police_brain.PoliceBrain`.
"""

from __future__ import annotations

from ..domain.board import Cell
from ..domain.brains_base import BrainView
from .pathing import bfs_distances, still_connected


class PoliceBarrier:
    def _would_seal(self, view: BrainView, barrier: Cell) -> bool:
        """Would this placement create a pocket nothing can leave - or enter?

        Deliberately not asked about a single *quarry* cell, which is why this
        takes none. The quarry used to be the freshest scent cell, which lags by
        a turn, and the live failure happened while their thief oscillated
        (6,6)<->(5,6): at the moment we barred (5,6) the quarry estimate WAS
        (5,6), so a quarry-based test asked whether barring a cell encloses that
        same cell, answered no, and let the seal through. The question is asked
        of the board, and then of every cell the thief could be on.

        With the rule unagreed an enclosed cell has no upside whatsoever - we
        cannot claim it and we cannot enter it - so the honest test is whether
        the board gains any enclosed open cell at all. That is 49 cheap checks
        and it cannot be fooled by a stale estimate.

        With the rule agreed, sealing is a win - but only when what we seal in
        is the thief. Walling off empty ground costs a barrier, costs the turn
        that placed it, and permanently removes cells from our own reach; over
        the played archive our police spent 287 turns unable to reach the thief
        at all, behind walls of its own making. The scent fix makes the
        difference checkable: an empty pocket is refused, a pocket the thief
        could be standing in is not.
        """
        size = view.board.size
        cells = [(r, c) for r in range(size) for c in range(size)]
        before = {c for c in cells if view.board.is_open(c) and view.board.is_enclosed(c)}
        trial = view.board.clone()
        trial.add_barrier(tuple(barrier))
        after = {c for c in cells if trial.is_open(c) and trial.is_enclosed(c)}
        # Never wall ourselves in. `still_connected` asks whether we can still
        # REACH the quarry, which passes right up until the turn the quarry
        # steps out of the component we just sealed ourselves into - and says
        # nothing about our own room to manoeuvre. Measured live vs uoh-ay26:
        # standing on (3,3) we barred (2,3), (3,2) and (3,4) on three
        # consecutive turns, spending three moves standing still while the thief
        # walked from distance 2 to unreachable. Fifteen barriers bought 31
        # turns with no path to it at all, and not one capture chance in three
        # sub-games. A pursuer that cannot move cannot pursue.
        if len(trial.open_neighbors(view.own_pos)) < self.OWN_EXITS_FLOOR:
            return True
        pockets = after - before
        if not pockets:
            return False
        if not view.claim_enclosure:
            return True
        if not view.opp_cells:
            return False  # no fix to judge it by: the agreed rule is the licence
        return not any(cell in pockets for cell in view.opp_cells)

    def _barrier_play(self, view: BrainView, target: Cell, b_max: float) -> Cell | None:
        left = view.barrier_quota - view.barriers_used
        if left <= 0:
            return None
        # With a fix in hand the belief peak is the weaker of two estimates, and
        # spending a barrier on it is worse than doing nothing: the pounce has
        # already declined every cell we can reach, so a placement here goes on
        # ground the tracker says the thief is *not* on. That is how 157
        # barriers bought 287 turns of being walled away from it.
        if self._where and self._where.get(target, 0.0) <= 0.0:
            self._recent.append(b_max)
            return None
        # Compare against the window BEFORE this turn joins it, so the test is
        # "has the posterior just sharpened relative to recent history".
        reference = max(self._recent) if self._recent else b_max
        self._recent.append(b_max)
        sharp = max(self.p.belief_floor, self.p.kill_shot_ratio * reference)
        adjacent_open = [c for c in view.board.neighbors4(view.own_pos) if view.board.is_open(c)]
        # Kill shot: our sharpest posterior sits on a cell we can bar now (#46).
        if b_max >= sharp and target in adjacent_open:
            return target
        if left <= self.p.endgame_reserve:
            return None
        # Corner seal: cornered belief mass close by - pinch its exit.
        if b_max >= max(self.p.belief_floor, self.p.seal_ratio * reference):
            dist = bfs_distances(view.board, view.own_pos)
            if dist.get(target, 99) <= self.p.seal_distance and self._is_cornered(view, target):
                for cell in adjacent_open:
                    if target in view.board.neighbors4(cell) and cell != target and \
                            still_connected(view.board, cell, view.own_pos, target):
                        return cell
        return None

    def _is_cornered(self, view: BrainView, cell: Cell) -> bool:
        n = view.board.size
        edges = (cell[0] in (0, n - 1)) + (cell[1] in (0, n - 1))
        return edges >= 1 and len(view.board.open_neighbors(cell)) <= 2
