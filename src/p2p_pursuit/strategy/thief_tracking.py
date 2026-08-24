"""Where the pursuer is, and where it is going next - as a mixin.

Split out of :mod:`.thief_brain` (§3.2, mixin strategy ch. 4.2). One concern:
turning the opponent's served scent field into a cell and a heading. The trail
is kept across turns, the projection extrapolates it, and the distance is the
only number the decision needs back. Nothing here chooses a move.
"""

from __future__ import annotations

from ..domain.board import Cell
from ..domain.brains_base import BrainView
from .pathing import bfs_distances


class ThiefTracking:
    #: Collinear barriers before a row or column reads as a wall being built.
    def _track_trail(self, view: BrainView) -> None:
        """Freshest cell of the PURSUER's scent trail, turn over turn."""
        scent = view.opp_scent
        fresh = None
        if max(max(row) for row in scent) >= self.p.thief_fresh_min:
            fresh = max(((r, c) for r in range(view.board.size)
                         for c in range(view.board.size)),
                        key=lambda cell: scent[cell[0]][cell[1]])
        self._prev_fresh, self._fresh = self._fresh, fresh


    def _project(self, view: BrainView, peak: Cell) -> Cell | None:
        """Where the pursuer is heading.

        Preferred signal is its scent-trail displacement: the police brain
        established in v3 that the belief peak jitters under hint noise and the
        trail does not, but the thief kept using the peak. The peak remains the
        fallback for turns where the trail is too stale to testify.
        """
        fresh, prev = self._fresh, self._prev_fresh
        if fresh is not None and prev is not None:
            dr, dc = fresh[0] - prev[0], fresh[1] - prev[1]
            if abs(dr) + abs(dc) == 1:
                lead = (fresh[0] + dr * 2, fresh[1] + dc * 2)
                if view.board.is_open(lead):
                    return lead
                near = (fresh[0] + dr, fresh[1] + dc)
                return near if view.board.is_open(near) else fresh
        if self._prev_peak is None:
            return None
        dr, dc = peak[0] - self._prev_peak[0], peak[1] - self._prev_peak[1]
        if abs(dr) + abs(dc) != 1:
            return None
        lead = (peak[0] + dr, peak[1] + dc)
        return lead if view.board.is_open(lead) else peak


    def _pursuer_distance(self, view: BrainView, peak: Cell) -> int:
        """Barrier-aware distance to the pursuer's most likely cell.

        Manhattan under-estimates around barriers, so the thief used to juke
        while the police was walled off - and juking costs escape speed.
        """
        return bfs_distances(view.board, view.own_pos).get(peak, view.board.size * 2)
