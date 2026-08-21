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
from .predict import spread, strike_zone

# The weights live in params.Doctrine so the offline search can address them;
# `w_trail` is the weight on the trail-derived pursuer cell against the diffuse
# posterior, and `thief_fresh_min` is the intensity below which the pursuer's
# trail is too stale to testify. The band that marks a cell of our OWN trail as
# stale enough to lie about is not searched: it is fixed by the decay schedule.
STALE_LOW, STALE_HIGH = 0.25, 0.65


class ThiefBrain(BrainBase):
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

    def _pick_move(self, view: BrainView) -> Decision:
        if view.sub_game != self._sub_game or view.step <= 1:
            self._sub_game, self._last_move, self._run_len = view.sub_game, None, 0
            self._prev_peak = self._fresh = self._prev_fresh = None
            self._strike = {}
            self._prev_cell = None
        self._track_trail(view)
        # Where the pursuer is now, and therefore which cells it can take on its
        # next move - the cells this thief must not be standing on. Both come
        # from the exact fix; with no fix they stay empty and the older,
        # belief-driven terms carry the turn as they always did.
        self._strike = self._danger(view)
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

    def _danger(self, view: BrainView) -> dict[Cell, float]:
        """Probability that the pursuer can be on each cell after its next move.

        Two steps of inference from one exact fix: spread it over the moves the
        pursuer has made since the field was written (biased toward closing,
        because a pursuer closes), then over the move it is about to make. The
        second spread is the point - under strict alternation the thief commits
        first, so a cell that is merely *next to* the pursuer is not near it, it
        is inside it.
        """
        if view.opp_fix is None:
            return {}
        where = spread(view.board, view.opp_fix, view.own_pos,
                       steps=view.opp_fix_lag, bias=self.p.chase_bias)
        return strike_zone(view.board, where)

    def _danger_at(self, view: BrainView, pos: Cell, threat: float) -> float:
        """How likely this cell is to end the sub-game, if we finish our move on it.

        Two ways, and the second is why the first is not enough. The pursuer can
        *step* onto it - that is the strike map. It can also *bar* our way out,
        and the set of cells it can bar is exactly the set it can step onto, so
        the same map answers both: multiply the strike values of our exits and
        that is the chance it can seal every one of them.

        The seal term is worth points only where the two teams agreed that an
        enclosed thief is captured. Where they did not, a sealed pocket is a
        *survival*, and it is how the reference peer beat us on 2026-08-01 - it
        sat in one for 27 turns while our police finished outside its own wall.
        Penalising the same geometry under both rulesets would throw that away.
        """
        danger = self._strike.get(pos, 0.0)
        if not view.claim_enclosure or threat <= 0.0:
            return danger
        exits = view.board.open_neighbors(pos)
        if not exits:
            return danger + threat        # already enclosed: nothing left to seal
        seal = 1.0
        for cell in exits:
            seal *= self._strike.get(cell, 0.0)
        return danger + seal * threat

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
    #: Collinear barriers before a row or column reads as a wall being built.
    #: Three, because that is what najamjad's column 3 held on their turn 7 and
    #: the escape it warns about expires on turn 9 - at four the warning arrives
    #: on the last turn it is still actionable, and at two every scattered pair
    #: of barriers is a wall.
    WALL_MIN = 3

    def _safe_exits(self, view: BrainView, pos: Cell) -> int:
        """How many ways out of ``pos`` the pursuer cannot also be standing on.

        Counted one ply further out than :meth:`_danger_at`. That term asks
        whether the pursuer can take the cell we are about to occupy; this asks
        whether, having occupied it, we will have anywhere to go - the pursuer
        moves once more before our next move resolves, so the cells it can
        reach in ``lag + 2`` are the ones our exits must avoid.

        This is the quantity a cut-off collapses and a chase does not.
        `w_mobility` counts open neighbours, which scores a pocket as roomy
        right up to the turn its mouth closes, and every archetype in the pool
        that merely chases fails to catch this thief at all. The one pursuer
        that beats it is our own police, whose whole method is to take the
        ground rather than close the distance.
        """
        exits = [pos, *view.board.open_neighbors(pos)]
        if view.opp_fix is None:
            return len(exits)
        theirs = bfs_distances(view.board, view.opp_fix)
        reach = view.opp_fix_lag + 2
        return sum(1 for cell in exits if theirs.get(cell, 99) > reach)

    def _wall_line(self, view: BrainView) -> set[Cell] | None:
        """The row or column currently being walled, projected to completion.

        A cage is not built cell by cell out of nowhere - it is a *line*, and a
        line declares itself long before it closes. Measured on najamjad's cage:
        column 3 held three collinear barriers by their turn 7 and four by turn
        9, and turn 9 is the last turn from which the escape still survives. So
        the signal exists inside the deadline, which is the one thing
        `_lifeboat` could not manage - that term does not become non-flat until
        step 11, two turns after the door has shut.

        Barriers are public and truthful by rule, so this reads only what the
        opponent has already declared.
        """
        board, size = view.board, view.board.size
        best: set[Cell] | None = None
        best_count = self.WALL_MIN - 1
        for i in range(size):
            for line in ({(i, c) for c in range(size)}, {(r, i) for r in range(size)}):
                count = sum(1 for cell in line if not board.is_open(cell))
                if count > best_count:
                    best, best_count = line, count
        return best

    def _wall_side(self, view: BrainView, pos: Cell) -> int:
        """Room we would hold if the forming wall closed, and only if we are on
        the *builder's* side of it.

        The counter-intuitive half, and the one the archive actually supports: a
        wall-builder walls away from itself and then crosses to finish the trap.
        najamjad's police built column 3 while standing in column 2, walked out
        through its own last gap on turn 15, and sealed it behind itself on turn
        17 - so the side that looked safe (ours, away from them) was the side
        they were coming to, and the side that looked mad (theirs) was the one
        that ended up empty. Forced-escape runs confirm it: crossing to their
        side on any turn up to 9 survives with a private half of the board.

        The value is the room on the builder's side **less the steps needed to
        reach it**, which is what makes it a gradient rather than a verdict. A
        first version returned that room only once we were already across, and
        measured identically at every weight from 0 to 1: the thief cannot cross
        a wall in one ply, so every move it could actually make scored zero and
        the term never steered anything. A reward you cannot reach in one step
        is not a reward, it is a constant.

        Zero when no wall is forming, so this is silent on an open board, and
        zero once the wall has closed - by then it is advice about a door that
        no longer exists, and `w_trap` owns what is left.
        """
        line = self._wall_line(view)
        pursuer = view.opp_fix if view.opp_fix is not None else view.opp_lead
        if line is None or pursuer is None or pursuer in line:
            return 0
        trial = view.board.clone()
        for cell in line:
            trial.add_barrier(cell)
        theirs = bfs_distances(trial, pursuer)
        if pos in line:
            # Standing in the gap *is* the crossing, and an earlier version
            # scored it zero because the cell belongs to the projected wall.
            # That built a gradient that walked the thief up to the door and
            # then forbade the step through it - measured: the escape move
            # scored 0 against 20 for every move away from it, at every weight
            # up to twelve times the searchable maximum.
            return len(theirs)
        if pos in theirs:                       # already on their side of it
            return len(theirs)
        gaps = [cell for cell in line if view.board.is_open(cell)]
        if not gaps:                            # sealed: no crossing left to plan
            return 0
        here = bfs_distances(view.board, pos)
        steps = min((here[gap] for gap in gaps if gap in here), default=None)
        if steps is None:
            return 0
        return max(0, len(theirs) - steps)

    def _lifeboat(self, view: BrainView, pos: Cell) -> int:
        """Biggest room we could still be sealed into **alone**, from ``pos``.

        The one quantity that answers a cage, and it is not any of the ones
        above. Measured on najamjad's wall, 2026-08-20: region size, escape
        room, territory and the two-barrier lookahead all have **spread 0** for
        every legal move at every step of the build - identical scores, so no
        weight on them can steer. They are flat because the board really is
        symmetric while the wall is going up; what is *not* symmetric is which
        side the pursuer ends on, and that is what this measures.

        For each cheap cut of the board we could still cross in time, we ask:
        if it closed, would we be on the side without the pursuer, and how big
        is that side? A large answer is a survival that does not depend on
        out-running anybody. Returns the board area when no cut threatens, so
        the term is silent on an open board and only speaks near a wall.

        Three bounds keep it affordable, and each is a fact about walls rather
        than a shortcut: a cut needs a wall to continue, so we do nothing until
        one exists (``CUT_MIN_BARRIERS``); its cells lie beside a barrier or on
        the rim, which is the only place a wall can grow; and the two halves of
        a cut are near each other, because a cut made of two distant cells is
        two holes, not a wall. Unbounded this is 49-choose-2 BFS per candidate
        move per turn, which is minutes per sub-game - measured.
        """
        area = view.board.size * view.board.size
        pursuer = view.opp_fix if view.opp_fix is not None else view.opp_lead
        board = view.board
        if pursuer is None or pursuer == pos or len(board.barriers) < self.CUT_MIN_BARRIERS:
            return area
        here = bfs_distances(board, pos)
        if pursuer not in here:                     # already sealed apart: safe
            return len(here)
        seam = [c for c in here
                if c not in (pos, pursuer)
                and (any(not board.is_open(n) for n in board.neighbors4(c))
                     or c[0] in (0, board.size - 1) or c[1] in (0, board.size - 1))]
        best = 0
        for i, a in enumerate(seam):
            for b in seam[i + 1:]:
                if max(abs(a[0] - b[0]), abs(a[1] - b[1])) > self.CUT_SPAN:
                    continue
                trial = board.clone()
                trial.add_barrier(a)
                trial.add_barrier(b)
                room = bfs_distances(trial, pos)
                if pursuer not in room and len(room) > best:
                    best = len(room)
        return best or area

    def _escape_room(self, view: BrainView, pos: Cell) -> int:
        """Cells reachable from ``pos`` without walking through the pursuer.

        The quantity a corner actually collapses, and the one a plain Voronoi
        count misses: ground on the far side of the pursuer is not ours in any
        sense that helps, because reaching it means passing through it.
        """
        if not self._strike:
            return view.board.size * view.board.size
        trial = view.board.clone()
        for cell, chance in self._strike.items():
            if chance >= self.CLOSED and cell != pos:
                trial.add_barrier(cell)
        return len(bfs_distances(trial, pos))

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
