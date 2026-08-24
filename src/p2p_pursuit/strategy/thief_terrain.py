"""How dangerous the ground is, and how much of it is left - as a mixin.

Split out of :mod:`.thief_brain` so both files stay inside the guidelines'
150-line limit (§3.2), using the mixin strategy for a class carrying more than
one responsibility (ch. 4.2). One concern: reading the board. Every method here
is a pure question about terrain given a position - the danger field, the wall
the police is building and which side of it we are on, how many exits and how
much room remain. None of them decides anything; the decision stays in
:class:`~.thief_brain.ThiefBrain`.
"""

from __future__ import annotations

from ..domain.board import Cell
from ..domain.brains_base import BrainView
from .pathing import bfs_distances
from .predict import spread, strike_zone


class ThiefTerrain:
    #: Three, because that is what najamjad's column 3 held on their turn 7 and
    #: the escape it warns about expires on turn 9 - at four the warning arrives
    #: on the last turn it is still actionable, and at two every scattered pair
    #: of barriers is a wall.
    WALL_MIN = 3

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
