"""Thief doctrine v4 (STRATEGY.md 6): risk-aware evasion, scent-aware pathing,
scent-consistent lying.

v3 brought the claim-radius risk term (cells within 2 of the police belief cloud
invite claims and kill shots), two-ply mobility, forward-projection risk and
situational juking. v4 closes four gaps, three of which are cases where the
thief had simply not been given a lesson the police already learned:

* **Signal quality.** Forward projection read the pursuer's velocity off the
  belief peak, which v3 established jitters under hint noise; it now reads the
  pursuer's scent trail, as the police does, and keeps the peak as fallback.
* **Barrier awareness.** The "am I being chased" test used Manhattan distance,
  which under-estimates around barriers - so the thief juked while the pursuer
  was walled off, and juking costs escape speed.
* **Corner discipline** no longer switches off at half-time; it scales with the
  pursuer's remaining barrier quota, which is public because barriers are
  declared.
* **Deception.** The lie pointed at the single furthest stale cell of a scent
  field we transmit ourselves, making it a deterministic function of public
  data. It is now sampled with our private rng.
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
W_TRAIL = 0.7   # weight on the trail-derived pursuer cell vs the diffuse posterior
STAY_PENALTY = 1.2
CORNER_PENALTY = 0.5
JUKE_PENALTY = 0.6
JUKE_RANGE = 3
STALE_LOW, STALE_HIGH = 0.25, 0.65
FRESH_MIN = 0.7   # below this the pursuer's trail is too stale to testify
LIE_CANDIDATES = 3


class ThiefBrain(BrainBase):
    def __init__(self) -> None:
        self._last_move: str | None = None
        self._run_len = 0
        self._prev_peak: Cell | None = None
        self._fresh: Cell | None = None
        self._prev_fresh: Cell | None = None
        self._sub_game: int | None = None

    def _pick_move(self, view: BrainView) -> Decision:
        if view.sub_game != self._sub_game or view.step <= 1:
            self._sub_game, self._last_move, self._run_len = view.sub_game, None, 0
            self._prev_peak = self._fresh = self._prev_fresh = None
        self._track_trail(view)
        centroid = scent_centroid(view.own_scent)
        peak = view.belief.argmax()
        projected = self._project(view, peak)
        chased = self._pursuer_distance(view, peak) <= JUKE_RANGE

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
            # The pursuer's own trail is a far better estimate of it than our
            # posterior: measured, our belief of the police sits 1.85 cells off
            # (26% exact) while its freshest served cell is where it stood one
            # step ago - and one step ago bounds where it can be now. Fleeing a
            # posterior this diffuse means fleeing a phantom, which is precisely
            # how a distance-maximising evader walks into a pursuer.
            if self._fresh is not None:
                expected = W_TRAIL * dist.get(self._fresh, view.board.size * 2) \
                    + (1.0 - W_TRAIL) * expected
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
            # Corner discipline for the WHOLE game, scaled by how many barriers
            # the pursuer still holds. It used to switch off at half-time, which
            # invited edge-hugging in exactly the phase where a police with an
            # unspent quota can seal a pocket. Barriers are declared publicly,
            # so the remaining quota is knowable rather than guessed.
            spent = len(view.board.barriers)
            threat = max(0.0, (view.barrier_quota - spent) / max(view.barrier_quota, 1))
            if view.step <= view.survival_threshold // 2 or threat > 0.0:
                n = view.board.size
                edges = (pos[0] in (0, n - 1)) + (pos[1] in (0, n - 1))
                early = view.step <= view.survival_threshold // 2
                s -= CORNER_PENALTY * edges * (1.0 if early else threat)
            return s + view.rng.random() * 1e-3

        # "Never STAY twice" (STRATEGY.md) is now enforced, not merely penalised:
        # a second consecutive STAY re-emits on the same cell and hands the
        # pursuer a sharpening posterior for free.
        moves = list(view.board.legal_moves(view.own_pos))
        if self._last_move == "STAY":
            moves = [m for m in moves if m != "STAY"] or moves
        best = max(moves, key=score)
        self._run_len = self._run_len + 1 if best == self._last_move else 1
        self._last_move = best
        self._prev_peak = peak
        return Decision(move=best)

    def _track_trail(self, view: BrainView) -> None:
        """Freshest cell of the PURSUER's scent trail, turn over turn."""
        scent = view.opp_scent
        fresh = None
        if max(max(row) for row in scent) >= FRESH_MIN:
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

    def _mobility2(self, view: BrainView, pos: Cell) -> float:
        """Two-ply openness: are this cell's exits themselves well-connected?"""
        return sum(len(view.board.open_neighbors(n))
                   for n in view.board.open_neighbors(pos)) / 4.0

    def hint_plan(self, view: BrainView, decision: Decision) -> tuple[str, str]:
        """Scent-consistent lie: claim a stale region our decayed trail supports.

        Sampled from the few furthest stale cells with our PRIVATE rng, never
        the single furthest. We transmit the scent field, so an opponent can
        recompute any deterministic function of it: picking the argmax made the
        lie derivable from public data - and therefore an admission of where we
        are not. Randomising leaves them a distribution instead of an answer.
        """
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
            ranked = sorted(stale, reverse=True,
                            key=lambda p: abs(p[0] - own[0]) + abs(p[1] - own[1]))
            pool = ranked[:LIE_CANDIDATES]
            return region_of(pool[view.rng.randrange(len(pool))], view.board.size), "lie"
        from .police_brain import OPPOSITE

        return OPPOSITE.get(region_of(view.own_pos, view.board.size), "north"), "lie"
