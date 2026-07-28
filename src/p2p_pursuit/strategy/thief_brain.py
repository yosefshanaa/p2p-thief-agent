"""Thief doctrine v3 (STRATEGY.md 3): risk-aware evasion, scent-aware pathing,
scent-consistent lying.

v3 over v2: a claim-radius risk term (cells within 2 of the police belief
cloud invite claims and kill-shots), two-ply mobility (avoid entering
pockets whose exits are cramped), forward-projection risk (avoid where the
pursuer is *heading* - the mirror of velocity-lead pursuit), and situational
juking (zigzag only while closely chased, where straight flight is fatal).
"""

from __future__ import annotations

from ..domain.board import Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.hints import region_of
from ..domain.rules import Decision
from .pathing import bfs_distances, scent_centroid

W_MOBILITY = 0.5
W_MOBILITY2 = 0.25
W_CENTROID = 0.4
W_RISK = 3.0
W_LEAD_RISK = 1.5
STAY_PENALTY = 1.2
CORNER_PENALTY = 0.5
JUKE_PENALTY = 0.6
JUKE_RANGE = 3
STALE_LOW, STALE_HIGH = 0.25, 0.65


class ThiefBrain(BrainBase):
    def __init__(self) -> None:
        self._last_move: str | None = None
        self._run_len = 0
        self._prev_peak: Cell | None = None
        self._sub_game: int | None = None

    def _pick_move(self, view: BrainView) -> Decision:
        if view.sub_game != self._sub_game or view.step <= 1:
            self._sub_game, self._last_move, self._run_len = view.sub_game, None, 0
            self._prev_peak = None
        centroid = scent_centroid(view.own_scent)
        peak = view.belief.argmax()
        projected = self._project(view, peak)
        chased = self._peak_distance(view, peak) <= JUKE_RANGE

        def score(move: str) -> float:
            pos = target_of(view.own_pos, move)
            dist = bfs_distances(view.board, pos)
            expected = risk = 0.0
            for r in range(view.board.size):
                for c in range(view.board.size):
                    b = view.belief.grid[r][c]
                    if b <= 0.0:
                        continue
                    d = dist.get((r, c), view.board.size * 2)
                    expected += b * d
                    if d <= 2:  # claim / kill-shot radius around likely police cells
                        risk += b
            s = expected - W_RISK * risk
            if projected is not None and dist.get(projected, 99) <= 2:
                s -= W_LEAD_RISK  # he is heading here: do not be here when he arrives
            s += W_MOBILITY * len(view.board.open_neighbors(pos))
            s += W_MOBILITY2 * self._mobility2(view, pos)
            if centroid is not None:
                s += W_CENTROID * (abs(pos[0] - centroid[0]) + abs(pos[1] - centroid[1]))
            if move == "STAY":
                s -= STAY_PENALTY  # re-emission concentrates our trail (never camp)
            if chased and move == self._last_move and self._run_len >= 2:
                s -= JUKE_PENALTY  # juke under close pursuit: straight flight is lethal
            if view.step <= view.survival_threshold // 2:
                n = view.board.size
                edges = (pos[0] in (0, n - 1)) + (pos[1] in (0, n - 1))
                s -= CORNER_PENALTY * edges
            return s + view.rng.random() * 1e-3

        best = max(view.board.legal_moves(view.own_pos), key=score)
        self._run_len = self._run_len + 1 if best == self._last_move else 1
        self._last_move = best
        self._prev_peak = peak
        return Decision(move=best)

    def _project(self, view: BrainView, peak: Cell) -> Cell | None:
        """The pursuer's next likely cell, from its belief-peak velocity."""
        if self._prev_peak is None:
            return None
        dr, dc = peak[0] - self._prev_peak[0], peak[1] - self._prev_peak[1]
        if abs(dr) + abs(dc) != 1:
            return None
        lead = (peak[0] + dr, peak[1] + dc)
        return lead if view.board.is_open(lead) else peak

    def _peak_distance(self, view: BrainView, peak: Cell) -> int:
        return abs(peak[0] - view.own_pos[0]) + abs(peak[1] - view.own_pos[1])

    def _mobility2(self, view: BrainView, pos: Cell) -> float:
        """Two-ply openness: are this cell's exits themselves well-connected?"""
        return sum(len(view.board.open_neighbors(n))
                   for n in view.board.open_neighbors(pos)) / 4.0

    def hint_plan(self, view: BrainView, decision: Decision) -> tuple[str, str]:
        """Scent-consistent lie: claim the stale region our decayed trail supports."""
        if view.rng.random() < 0.15:
            return region_of(view.own_pos, view.board.size), "truth"
        stale = [
            (r, c)
            for r, row in enumerate(view.own_scent)
            for c, v in enumerate(row)
            if STALE_LOW <= v <= STALE_HIGH
        ]
        if stale:
            own = view.own_pos
            far = max(stale, key=lambda p: abs(p[0] - own[0]) + abs(p[1] - own[1]))
            return region_of(far, view.board.size), "lie"
        from .police_brain import OPPOSITE

        return OPPOSITE.get(region_of(view.own_pos, view.board.size), "north"), "lie"
