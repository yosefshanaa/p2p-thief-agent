"""Police doctrine v3 (STRATEGY.md 3): lead pursuit, barrier phases, herding lies.

v3 over v2: velocity-lead interception (aim where the thief is *going*, not
where it was), thresholds recalibrated to the scent-posterior scale, and a
a disciplined claim policy - every claim leaks our exact position to the
thief, so claims fire only on strong posteriors (0.15) or in desperation.
Every placement passes the flood-fill self-trap veto; two barriers stay in
reserve for the endgame.
"""

from __future__ import annotations

from ..domain.board import Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.hints import region_of
from ..domain.rules import Decision
from .pathing import bfs_distances, still_connected

# Under scent evidence the posterior spreads over ~5-8 live cells, so the
# top-cell mass rarely exceeds ~0.3; thresholds are calibrated to that scale.
KILL_SHOT_BELIEF = 0.30
SEAL_BELIEF = 0.20
SEAL_DISTANCE = 3
ENDGAME_RESERVE = 2

OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "northeast": "southwest", "southwest": "northeast",
            "northwest": "southeast", "southeast": "northwest", "center": "north"}


class PoliceBrain(BrainBase):
    claim_threshold = 0.15

    def __init__(self) -> None:
        self._prev_fresh: Cell | None = None
        self._sub_game: int | None = None

    def _decide_move(self, view: BrainView) -> Decision:
        if view.sub_game != self._sub_game or view.step <= 1:
            self._sub_game, self._prev_fresh = view.sub_game, None
        peak = view.belief.argmax()
        b_max = view.belief.grid[peak[0]][peak[1]]
        barrier = self._barrier_play(view, peak, b_max)
        if barrier is not None:
            return Decision(move="STAY", barrier=barrier)
        target = self._intercept_target(view) or peak
        return self._pursue(view, target)

    def _intercept_target(self, view: BrainView) -> Cell | None:
        """Solve the pursuit curve: meet the thief along its scent-trail velocity.

        The freshest served-scent cell marks where the thief *was*; its
        displacement between reveals is the thief's velocity - a cleaner
        signal than belief-peak jitter. Project position(t) = fresh + v*(1+k)
        and aim at the first projected cell we can reach in time.
        """
        scent = view.opp_scent
        top = max(max(row) for row in scent)
        fresh = None
        if top >= 0.7:  # only a genuinely fresh trail testifies
            fresh = max(((r, c) for r in range(view.board.size)
                         for c in range(view.board.size)),
                        key=lambda cell: scent[cell[0]][cell[1]])
        prev, self._prev_fresh = self._prev_fresh, fresh
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

    def _barrier_play(self, view: BrainView, target: Cell, b_max: float) -> Cell | None:
        left = view.barrier_quota - view.barriers_used
        if left <= 0:
            return None
        adjacent_open = [c for c in view.board.neighbors4(view.own_pos) if view.board.is_open(c)]
        # Kill shot: strong belief on a cell we can bar right now (captures, #46).
        if b_max >= KILL_SHOT_BELIEF and target in adjacent_open:
            return target
        # Corner seal: cornered belief mass close by - pinch its exit, keep a reserve.
        if left <= ENDGAME_RESERVE or b_max < SEAL_BELIEF:
            return None
        dist = bfs_distances(view.board, view.own_pos)
        if dist.get(target, 99) > SEAL_DISTANCE or not self._is_cornered(view, target):
            return None
        for cell in adjacent_open:
            if target in view.board.neighbors4(cell) and cell != target and \
                    still_connected(view.board, cell, view.own_pos, target):
                return cell
        return None

    def _is_cornered(self, view: BrainView, cell: Cell) -> bool:
        n = view.board.size
        edges = (cell[0] in (0, n - 1)) + (cell[1] in (0, n - 1))
        return edges >= 1 and len(view.board.open_neighbors(cell)) <= 2

    def _pursue(self, view: BrainView, target: Cell) -> Decision:
        dist_from_target = bfs_distances(view.board, target)

        def score(move: str) -> tuple:
            pos = target_of(view.own_pos, move)
            d = dist_from_target.get(pos, 9999)
            near = view.belief.mass_in({
                (pos[0] + dr, pos[1] + dc) for dr in (-2, -1, 0, 1, 2) for dc in (-2, -1, 0, 1, 2)
            })
            return (d, -near, view.rng.random())

        best = min(view.board.legal_moves(view.own_pos), key=score)
        return Decision(move=best)

    def should_claim(self, view: BrainView, new_pos: Cell) -> bool:
        belief_here = view.belief.grid[new_pos[0]][new_pos[1]]
        desperate = view.steps_remaining <= 8 and belief_here >= 0.05
        return belief_here >= self.claim_threshold or desperate

    def hint_plan(self, view: BrainView, decision: Decision) -> tuple[str, str]:
        """Herding lie: claim to close in from the opposite side of our true region."""
        if view.rng.random() < 0.2:
            return region_of(view.own_pos, view.board.size), "truth"
        true_region = region_of(view.own_pos, view.board.size)
        return OPPOSITE.get(true_region, "north"), "lie"
