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

v6 replaces the signal all of that rests on. "The pursuer's scent trail" meant
the argmax of its served field, and mining the played archive showed that argmax
names the emitter's cell 11% of the time - the field saturates, 91% of served
fields have between 6 and 20 cells tied at the maximum, and ``max`` then returns
whichever tied cell row-major iteration reaches first. That is a bias toward the
top-left corner, and our thief spent `w_trail` fleeing it: 11 of its 14 deaths in
the archive are in the bottom and right edges. :mod:`..domain.tracking` inverts
the field instead, which is exact, so the pursuer's cell is now known rather
than guessed.

Knowing it exactly makes one term possible that no amount of tuning could
substitute for: **do not end the move where the pursuer can step next**. Across
35 archived sub-games this thief finished its move inside that reach 43 times
and was taken 14 times, and both losses to gal-roy1 are the same picture - it
walked to a cell orthogonally adjacent to a pursuer whose exact position its own
scent feed was carrying.
"""

from __future__ import annotations

from ..domain.board import Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.hints import region_of
from ..domain.rules import Decision
from .mixing import choose
from .params import Doctrine, active
from .pathing import bfs_distances, scent_centroid
from .thief_terrain import ThiefTerrain
from .thief_tracking import ThiefTracking

# The weights live in params.Doctrine so the offline search can address them;
# `w_trail` is the weight on the trail-derived pursuer cell against the diffuse
# posterior, and `thief_fresh_min` is the intensity below which the pursuer's
# trail is too stale to testify. The band that marks a cell of our OWN trail as
# stale enough to lie about is not searched: it is fixed by the decay schedule.
STALE_LOW, STALE_HIGH = 0.25, 0.65

#: How many cells of a losing run are buried, counting back from the cell we
#: died on, and with what weight - the death cell always at 1.0, each earlier
#: cell linearly less. Not a doctrine key, because the measurement says there is
#: nothing to tune: see `_bury`.
GRAVE_TAIL = 1


class ThiefBrain(ThiefTerrain, ThiefTracking, BrainBase):
    def __init__(self, doctrine: Doctrine | None = None) -> None:
        self.p = doctrine or active()
        self._last_move: str | None = None
        self._run_len = 0
        self._prev_peak: Cell | None = None
        self._fresh: Cell | None = None
        self._prev_fresh: Cell | None = None
        self._sub_game: int | None = None
        self._strike: dict[Cell, float] = {}
        self._prev_cell: Cell | None = None
        #: Cells earlier sub-games of THIS series ended on when we were caught,
        #: each with the weight `_bury` gave it.
        #:
        #: A match is six sub-games from the same two signed starting cells, and
        #: without this the thief plays the sixth exactly as it played the
        #: first. Audited from `result.my_steps` in the sealed logs: of 22
        #: archived series and 67 thief sub-games, 38 ended in capture; eight
        #: series lost EVERY thief window and six of those lost them at the
        #: identical step - vibecode at step 14 on [6, 5] in three friendlies
        #: running, najamjad at 30, uoh-ay26 at 10 on [5, 5], orcai-mj at 16.
        #: Mixing does not fix it, because it varies the road and a funnel
        #: gathers every road. How hard this pushes is `w_grave`, per physics.
        self._graves: list[tuple[Cell, float]] = []
        self._last_step = 0
        #: Cells walked in the current sub-game, newest last - only so that a
        #: death can bury more than its final cell. See `GRAVE_TAIL`.
        self._walked: list[Cell] = []

    def _pick_move(self, view: BrainView) -> Decision:
        if view.sub_game != self._sub_game or view.step <= 1:
            # A previous sub-game that stopped short of the survival threshold
            # ended because we were caught, and `_prev_cell` is where. Inferred
            # rather than reported: the brain is never told the outcome, and a
            # new protocol field for it would have to be negotiated.
            if (self._sub_game is not None and self._prev_cell is not None
                    and 0 < self._last_step < view.survival_threshold):
                self._bury()
            self._sub_game, self._last_move, self._run_len = view.sub_game, None, 0
            self._prev_peak = self._fresh = self._prev_fresh = None
            self._strike = {}
            self._prev_cell = None
            self._walked = []
        self._track_trail(view)
        # Where the pursuer is now, and therefore which cells it can take on its
        # next move - the cells this thief must not be standing on. Both come
        # from the exact fix; with no fix they stay empty and the older,
        # belief-driven terms carry the turn as they always did.
        self._strike = self._danger(view)
        self._last_step = view.step
        self._walked.append(view.own_pos)
        # One BFS *per grave*, not one from where we stand: the term has to
        # measure each candidate's LANDING cell, and a single BFS from our own
        # position would give every candidate the same number and do nothing.
        # Graves are few - one per lost sub-game, at most five - and the board
        # is 7x7, so this is cheaper than the per-candidate search it replaces.
        graves = [(bfs_distances(view.board, cell), weight)
                  for cell, weight in self._graves] if self.p.w_grave > 0 else []
        centroid = scent_centroid(view.own_scent)
        peak = view.belief.argmax()
        projected = view.opp_lead or self._project(view, peak)
        chased = self._pursuer_distance(view, view.opp_fix or peak) <= self.p.juke_range
        # One BFS from the pursuer per turn, shared by every candidate: the
        # territory term needs *its* distances, not ours.
        pursuer = view.opp_fix or self._fresh or peak
        opp_dist = bfs_distances(view.board, pursuer) if pursuer is not None else {}
        unreachable = view.board.size * view.board.size
        # A pocket is only a trap while the pursuer can still seal its mouth.
        threat = max(0.0, (view.barrier_quota - len(view.board.barriers))
                     / max(view.barrier_quota, 1))

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
            if pursuer is not None and (view.opp_fix is not None or self._fresh is not None):
                expected = self.p.w_trail * dist.get(pursuer, view.board.size * 2) \
                    + (1.0 - self.p.w_trail) * expected
            s = expected - self.p.w_risk * risk
            # The one term that answers how this thief actually dies. Distance
            # and risk both treat the pursuer as a cloud; this treats it as an
            # agent with a move left to play, and refuses to hand it the cell.
            s -= self.p.w_strike * self._danger_at(view, pos, threat)
            if projected is not None and dist.get(projected, 99) <= 2:
                s -= self.p.w_lead_risk  # he is heading here: do not be here when he arrives
            s += self.p.w_mobility * len(view.board.open_neighbors(pos))
            s += self.p.w_safe2 * self._safe_exits(view, pos)
            s += self.p.w_mobility2 * self._mobility2(view, pos)
            # Room we own, and the trap gradient when it collapses. Openness
            # counts doors; this counts the space behind them that the pursuer
            # cannot reach first - the difference between a corridor with two
            # exits and a corridor with two exits the pursuer is standing in.
            if opp_dist:
                # Room we own, but only the room we can actually get *to*: a
                # Voronoi count walks straight through the pursuer, so an edge
                # run into a corner scores as roomy right up to the last turn.
                # 79% of this thief's deaths in the archive are on the bottom or
                # right edge, arrived at exactly that way.
                owned = min(self._territory(dist, opp_dist, unreachable),
                            self._escape_room(view, pos))
                s += self.p.w_territory * owned
                if owned < self.p.trap_floor:
                    s -= self.p.w_trap * (self.p.trap_floor - owned) * threat
            # Anticipatory, unlike `w_trap`: that one fires once we are already
            # in the pocket, which the archive says is several turns after the
            # last moment we could have left it.
            if self.p.w_lifeboat > 0:
                s += self.p.w_lifeboat * self._lifeboat(view, pos)
            # Anticipates the wall rather than the pocket, which is what the
            # measured turn-9 deadline requires - see `_wall_side`.
            if self.p.w_wall_side > 0:
                s += self.p.w_wall_side * self._wall_side(view, pos)
            if centroid is not None:
                s += self.p.w_centroid * (abs(pos[0] - centroid[0])
                                          + abs(pos[1] - centroid[1]))
            if move == "STAY":
                s -= self.p.stay_penalty  # re-emission concentrates our trail (never camp)
            if chased and move == self._last_move and self._run_len >= 2:
                s -= self.p.juke_penalty  # juke under close pursuit: straight flight is lethal
            # ...but a juke is a SIDESTEP, not a step backwards. Without this the
            # two terms conspire: taxing a repeated move while leaving the return
            # free makes A->B->A the cheapest sequence there is, and the thief
            # dithers on one cell while a monotone pursuer closes on it.
            if pos == self._prev_cell:
                s -= self.p.backtrack_penalty
            # Corner discipline for the WHOLE game, scaled by how many barriers
            # the pursuer still holds. It used to switch off at half-time, which
            # invited edge-hugging in exactly the phase where a police with an
            # unspent quota can seal a pocket. Barriers are declared publicly,
            # so the remaining quota is knowable rather than guessed. `threat` is
            # computed once per turn above, shared with the trap term.
            if view.step <= view.survival_threshold // 2 or threat > 0.0:
                n = view.board.size
                edges = (pos[0] in (0, n - 1)) + (pos[1] in (0, n - 1))
                early = view.step <= view.survival_threshold // 2
                s -= self.p.corner_penalty * edges * (1.0 if early else threat)
            # Where earlier sub-games of this series died. A funnel gathers
            # every road, so varying the road is not enough - the trap cell
            # itself has to become expensive. Scaled by `w_strike` so it is
            # decisive on the doctrine's own scale rather than a tunable
            # afterthought, and it only ever competes: a move that is better on
            # every other term still wins.
            if graves:
                near = max((weight * (self.p.grave_radius + 1 - d.get(pos, 99))
                            for d, weight in graves), default=0.0)
                if near > 0:
                    s -= self.p.w_grave * near
            return s + view.rng.random() * 1e-3

        # "Never STAY twice" (STRATEGY.md) is now enforced, not merely penalised:
        # a second consecutive STAY re-emits on the same cell and hands the
        # pursuer a sharpening posterior for free.
        moves = list(view.board.legal_moves(view.own_pos))
        if self._last_move == "STAY":
            moves = [m for m in moves if m != "STAY"] or moves
        best = choose(moves, score, self.p.mix_margin, view.rng, prefer=max)
        self._run_len = self._run_len + 1 if best == self._last_move else 1
        self._last_move = best
        self._prev_cell = view.own_pos
        self._prev_peak = peak
        return Decision(move=best)

    def _bury(self) -> None:
        """Record where the sub-game we just lost ended, and how we got there.

        Inferred rather than reported: the brain is never told the outcome, and
        a new protocol field for it would have to be negotiated. A window that
        stopped short of the survival threshold stopped because we were caught,
        and `_walked` says where.

        Only the final cell, and that is a measurement rather than a default.
        Burying the approach as well is the obvious generalisation - a cage
        kills you twenty turns before it closes, so the mistake is upstream of
        the grave - and over 3312 sub-games it is **worse than having no memory
        at all**: under `subtractive_chebyshev_v1` a tail of 1 is taken 28 times
        and a tail of 2 is taken 148, which is exactly the score of the term
        switched off; under `registered_v3`, 155 -> 176 -> 192 for tails 1, 2
        and 4.

        The reason is visible in a single trace against najamjad's cage. The
        thief dies on (2, 4), having come through (1, 4). A tail of 2 buries
        both - and (1, 4) is the only way *out* of that pocket, so the thief
        that has learned to avoid its own approach has learned to stay in the
        trap: it dies on (2, 4) at step 30 in all six windows, where burying the
        death cell alone gets it out in five of six.

        **The approach to a grave is the escape route from it.** That is why
        this is a constant and not a searchable key.
        """
        tail = [c for c in self._walked[-GRAVE_TAIL:] if c is not None]
        if not tail:
            tail = [self._prev_cell]
        for i, cell in enumerate(reversed(tail)):
            self._graves.append((cell, 1.0 - i / max(len(tail), 1)))
    #: A strike cell counts as closed when the pursuer is more likely than not
    #: to be able to take it. Not "any chance at all": under a lagged fix that
    #: would wall off thirteen cells, a quarter of the board, and leave the
    #: thief with nowhere that scores at all.
    CLOSED = 0.5
    #: No wall, no cut: below this the seam scan cannot find one and only costs
    #: time. Four is the fewest barriers that can reach across a 7x7 corner.
    CUT_MIN_BARRIERS = 4
    #: Chebyshev span between the two halves of a candidate cut. A wall grows
    #: from what is already there, so its next two cells are neighbours; two
    #: cells further apart than this are two separate holes, not a seal.
    CUT_SPAN = 2
    @staticmethod
    def _territory(mine: dict[Cell, int], theirs: dict[Cell, int],
                   unreachable: int) -> int:
        """Cells we reach strictly sooner than the pursuer (a Voronoi split).

        Ties go to the pursuer: arriving together is arriving into it. Cells it
        cannot reach at all are ours by default, which is what makes a sealed
        pocket read as *small* rather than safe - the pocket's own cells stay
        ours, and everything beyond the mouth stops being.
        """
        return sum(1 for cell, d in mine.items()
                   if d < theirs.get(cell, unreachable))

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
        if view.rng.random() < self.p.thief_truth_rate:
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
            pool = ranked[:self.p.lie_candidates]
            return region_of(pool[view.rng.randrange(len(pool))], view.board.size), "lie"
        from .police_brain import OPPOSITE

        return OPPOSITE.get(region_of(view.own_pos, view.board.size), "north"), "lie"
