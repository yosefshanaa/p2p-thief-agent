"""Where the thief is, and where to stand to meet it - as a mixin.

Split out of :mod:`.police_brain` (§3.2, mixin strategy ch. 4.2). One concern:
turning scent, trail and belief into a cell worth walking at - where the thief
probably is now, whether it is actually running, the trail-velocity
interception point, and the fallback when the argmax is unreachable. It never
decides a move or places a barrier; that stays in
:class:`~.police_brain.PoliceBrain`.
"""

from __future__ import annotations

from ..domain.board import Cell
from ..domain.brains_base import BrainView
from .pathing import bfs_distances
from .predict import spread


class PoliceTracking:
    def _evading(self, view: BrainView, quarry: Cell) -> bool:
        """Has the gap stopped closing? Then distance alone will not finish this."""
        gap = bfs_distances(view.board, view.own_pos).get(quarry, 99)
        self._gaps.append(gap)
        return len(self._gaps) == self._gaps.maxlen and gap >= self._gaps[0]

    def _thief_now(self, view: BrainView) -> dict[Cell, float]:
        """Probability over the thief's current cell, from the scent fix.

        Under a model that serves after emitting, the fix *is* the answer and
        this is a delta. Under ``book_v1`` the fix is one step old, so the mass
        is spread over the moves it could have made - weighted by `flee_bias`,
        because an evader that has just been located does not walk toward us.

        Empty when there is no fix, which is the first turn of a sub-game and
        any turn where the field could not be inverted uniquely. Everything that
        reads it must therefore still have a belief-based fallback.
        """
        if view.opp_fix is None:
            return {}
        return spread(view.board, view.opp_fix, view.own_pos,
                      steps=view.opp_fix_lag, bias=self.p.flee_bias)

    def _likeliest(self) -> Cell | None:
        """The single most probable cell for the thief right now."""
        return max(self._where, key=self._where.get) if self._where else None

    def _track_trail(self, view: BrainView) -> None:
        """Remember the freshest served-scent cell, turn over turn."""
        scent = view.opp_scent
        top = max(max(row) for row in scent)
        fresh = None
        if top >= self.p.police_fresh_min:  # only a genuinely fresh trail testifies
            fresh = max(((r, c) for r in range(view.board.size)
                         for c in range(view.board.size)),
                        key=lambda cell: scent[cell[0]][cell[1]])
        self._prev_fresh, self._fresh = self._fresh, fresh

    def _intercept_target(self, view: BrainView) -> Cell | None:
        """Solve the pursuit curve: meet the thief along its scent-trail velocity.

        The freshest served-scent cell marks where the thief *was*; its
        displacement between reveals is the thief's velocity - a cleaner
        signal than belief-peak jitter. Project position(t) = fresh + v*(1+k)
        and aim at the first projected cell we can reach in time.
        """
        # Two exact fixes make a real heading; the scent argmax the trail used
        # to be read from jitters across a saturated field, so `abs(dr)+abs(dc)
        # == 1` was rarely true and, when it was, was often true by accident.
        if view.opp_lead is not None and view.opp_fix is not None:
            dr = view.opp_lead[0] - view.opp_fix[0]
            dc = view.opp_lead[1] - view.opp_fix[1]
            fresh = view.opp_fix
            if abs(dr) + abs(dc) == 0:
                return None
            dr, dc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
        else:
            fresh, prev = self._fresh, self._prev_fresh
            if fresh is None or prev is None:
                return None
            dr, dc = fresh[0] - prev[0], fresh[1] - prev[1]
            if abs(dr) + abs(dc) != 1:
                return None
        mine = bfs_distances(view.board, view.own_pos)
        for k in range(5):  # thief is ~1 step past `fresh` now, +k more when we arrive
            cand = (fresh[0] + dr * (1 + k), fresh[1] + dc * (1 + k))
            if not view.board.is_open(cand):
                break
            if mine.get(cand, 99) <= k + 1:
                return cand
        return None

    def _next_best_cell(self, view: BrainView) -> Cell | None:
        """Where to step when the peak is under our own feet.

        The neighbouring cell with the most belief mass around it - NOT the
        globally second-best cell, which can sit across the board and abandons
        the probability cloud altogether (measurably worse against an evader
        that diffuses rather than flees).
        """
        def local_mass(cell: Cell) -> float:
            return view.belief.mass_in({
                (cell[0] + dr, cell[1] + dc)
                for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            })

        best, best_mass = None, -1.0
        for cell in view.board.neighbors4(view.own_pos):
            if view.board.is_open(cell) and local_mass(cell) > best_mass:
                best, best_mass = cell, local_mass(cell)
        return best
