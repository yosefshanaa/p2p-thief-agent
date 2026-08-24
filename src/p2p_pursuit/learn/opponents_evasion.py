"""The two archetypes built around taking the room away, or refusing to give
it up: an evader that reads the belief the way we do, and a cager that
spends its barrier quota walling a thief in.

Split out of :mod:`.opponents` (§3.2). Both exist because the lab was blind
to exactly what they do - see the module docstrings for the measurements."""

from __future__ import annotations

from ..domain.board import Board, Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.rules import Decision
from ..strategy.pathing import bfs_distances
from .opponents_base import FAR


class Evader(BrainBase):
    """The evader that actually beat us: an exact fix, and territory to stand on.

    Every other thief here reads the *belief* for the pursuer's cell, and the
    belief is a weak estimate - which is how the lab police converted 760 of 760
    sub-games while our live police went 0 for 6 against the two teams that
    evade for real. Those two held the gap at 2 and 3 for whole sub-games, which
    is not something a blind evader can do. So this one inverts the pursuer's
    own published field, exactly as our police inverts ours.

    Given the fix, the doctrine is two rules and neither is "run away":

    * **Never be catchable next turn.** We move first; a cell the pursuer can
      reach in one step is a cell we are captured on. That single constraint,
      and not distance, is what holds a gap open indefinitely.
    * **Among safe cells, keep the most doors.** Not distance, and - measured -
      not territory either: on an open board the count of cells you reach
      before the pursuer is monotone in distance from it, so a territory rule
      is a distance rule wearing a disguise, and both walk into the corner the
      pursuer is herding you toward. Ranking raw mobility first, centrality
      second, territory last is what actually holds. Against the police as it
      played the counted matches: territory-first is caught 40/40, mobility
      first 0/40.

    The result is the standoff from the archive rather than a chase: it sits at
    the edge of the pursuer's reach, in the open, and refuses to be herded.
    """

    def __init__(self, *, w_room: float = 1.0) -> None:
        self.w_room = w_room

    def hunter(self, view: BrainView) -> Cell | None:
        """The pursuer's cell, from the fix if we have one and the belief if not."""
        if view.opp_fix is not None and not view.opp_fix_lag:
            return view.opp_fix
        if len(view.opp_cells) == 1:
            return view.opp_cells[0]
        peak = view.belief.argmax()
        return peak if view.belief.grid[peak[0]][peak[1]] > 0.0 else None

    def _pick_move(self, view: BrainView) -> Decision:
        moves = view.board.legal_moves(view.own_pos)
        hunter = self.hunter(view)
        if hunter is None:
            return Decision(move=view.rng.choice(moves))
        theirs = bfs_distances(view.board, hunter)

        def score(move: str) -> tuple:
            pos = target_of(view.own_pos, move)
            gap = theirs.get(pos, FAR)
            mine = bfs_distances(view.board, pos)
            # Cells we reach strictly before the pursuer does. This is the
            # quantity a corner takes away, which is why it needs no corner rule.
            room = sum(1 for cell, ours_d in mine.items()
                       if ours_d < theirs.get(cell, FAR))
            # Lexicographic, and every distance-like quantity ranks BELOW
            # mobility. From (5,6) with the pursuer on (4,5), the roomier and
            # further cell is the corner (6,6), and two turns later the corner
            # is a coffin - which is how a distance- or territory-led evader is
            # caught 40 times in 40. Doors first, then the middle of the board,
            # then ground: 0 in 40 against the same pursuer.
            centre = (view.board.size - 1) / 2
            edge = abs(pos[0] - centre) + abs(pos[1] - centre)
            return (gap >= 2, len(view.board.open_neighbors(pos)), -edge,
                    self.w_room * room, view.rng.random())

        return Decision(move=max(moves, key=score))


class Cager(BrainBase):
    """The police that actually beat us: it spends barriers on doors, not on the thief.

    ``BarrierHappy`` walls the thief's own cell when the belief peak happens to
    sit next door. That is a *kill* shot, and a competent evader never offers
    it - which is why our thief survives it 62% of the time under book and 100%
    under subtractive. Nobody in the pool plays the thing that beat us.

    What beat us is a **cage**. orcai-mj took our thief 6 times in 6; gal-roy1
    and uoh-ay26 took it twice each. Read the causes in the archive and four of
    the eight counted deaths say ``barrier onto ...`` or ``enclosed`` - the
    pursuer never had to land on us, it shrank the room until there was none.
    All eight are on the outer ring or one step off it.

    So this brain optimises the quantity the archive says matters, the thief's
    *escape room* - cells the thief reaches strictly before we do - and it has
    two ways to shrink it:

    * **Seal.** A barrier may go on an orthogonal neighbour, so a police at the
      mouth of a pocket can close it. We seal the door that costs the thief the
      most room, and only inside `cage_range`, because at distance the metric
      measures which corner we stand in rather than anything about the thief.
    * **Herd.** Otherwise close, breaking ties by the room the step takes away.

    There was a second ordering here - room leading, gap breaking the ties - on
    the reading that our thief's 0-for-40 against it was the live loss reproduced.
    It was not. That police stood still: 0 moves in 1360 turns against `Evader`,
    one distinct cell for a whole 40-seed sequence, and 6% of turns moved even
    after the ordering was gated to close range. The room metric barely responds
    to a police step at any distance, so ranking by it first is a rule that
    prefers standing where it is, and the 40-0 it produced measured that rather
    than anything about evasion. Removed rather than tuned: our own police
    already takes ground for real, through `w_cut`, and it is in this pool as
    `mirror`.

    Like :class:`Evader` it inverts the opponent's published field rather than
    reading the belief, because a cage built around the wrong cell is free
    space. And it honours ``claim_enclosure``: against a peer that never agreed
    an enclosed thief is caught, completing the seal throws the sub-game away,
    so there it stops one door short and keeps the pocket enterable.
    """

    def __init__(self, *, seal_gain: int = 1, cage_range: int = 4) -> None:
        #: Ground the seal must take off the thief before it is worth forfeiting
        #: the move. 1, because a barrier legal to us is adjacent to us, and one
        #: of those takes a single cell far more often than it takes several: at
        #: 2 this brain places no barrier at all and is a plain chaser.
        self.seal_gain = seal_gain
        #: How close we must be before a barrier is worth a turn.
        self.cage_range = cage_range

    def quarry(self, view: BrainView) -> Cell | None:
        """The thief's cell: the fix if it is current, its projection if it lags.

        Under a lag-0 model the inversion is exact. Under a lagged one - book_v1
        serves the field a step late - the exact answer is a step stale, and
        that is still far better than the belief peak, which the archive puts
        right 11% of the time. orcai-mj caged us 6 times in 6 under book, so a
        cager that gives up whenever the model lags is not the opponent we met.
        """
        if view.opp_fix is not None and not view.opp_fix_lag:
            return view.opp_fix
        if view.opp_lead is not None and view.board.is_open(view.opp_lead):
            return view.opp_lead
        if view.opp_cells:
            grid = view.belief.grid
            return max(view.opp_cells, key=lambda c: grid[c[0]][c[1]])
        peak = view.belief.argmax()
        return peak if view.belief.grid[peak[0]][peak[1]] > 0.0 else None

    @staticmethod
    def _room(board: Board, thief: Cell, police: Cell,
              theirs: dict[Cell, int] | None = None) -> int:
        """Cells the thief reaches strictly before the police does.

        ``theirs`` is the thief's distance map, passed in wherever the caller
        already holds it: the five candidate moves of one turn share it, and
        this brain is the most expensive member of the pool to evaluate.
        """
        theirs = bfs_distances(board, thief) if theirs is None else theirs
        mine = bfs_distances(board, police)
        return sum(1 for cell, d in theirs.items() if d < mine.get(cell, FAR))

    def _decide_move(self, view: BrainView) -> Decision:
        thief = self.quarry(view)
        if thief is None:
            return self._pick_move(view)
        theirs = bfs_distances(view.board, thief)

        # A cage is a close-range weapon. At six steps the room metric is
        # dominated by which corner we happen to stand in - stepping off (0,0)
        # toward a thief on (3,3) *raises* its room from 33 to 37, because the
        # cells that were ties break its way - so a police that seals or herds
        # by room alone at range does neither. Close first, cage second.
        near = theirs.get(view.own_pos, FAR)
        if near <= self.cage_range and view.barrier_quota - view.barriers_used > 0:
            # What a barrier is worth is the ground it takes off the thief -
            # cells it can still reach - and NOT the Voronoi room `_room`
            # measures. The rules put a barrier on our own cell or an orthogonal
            # neighbour, and a cell next to the police is a cell the police
            # reaches first, so it is never in the thief's room: measured, the
            # best available room-gain was exactly 0 on all 1825 in-range turns
            # of a 40-seed sequence, which is why this brain placed no barrier in
            # its entire life and the pool still had no cage in it.
            #
            # Reachability is the measure that can be followed. A cage is a
            # sequence of barriers, and the early ones in the sequence buy no
            # room at all - they buy the wall that the last one closes - so a
            # greedy test against room can never start one, while a greedy test
            # against ground taken can.
            here_reach = len(bfs_distances(view.board, thief))
            best_cell, best_reach = None, here_reach
            # Neighbours only. A barrier on our own cell is legal by the letter
            # of the rules and useless by their spirit - it forfeits the move and
            # walls the square we are standing on - and taking it silently was
            # this brain's first bug: `safe_decision` rejected the placement,
            # substituted a bare STAY, and the cage sat at (0,0) for 35 steps.
            for cell in view.board.neighbors4(view.own_pos):
                if not view.board.is_open(cell) or cell == thief:
                    continue
                walled = view.board.clone()
                walled.add_barrier(cell)
                # Sealing the last door wins only against a peer that agreed an
                # enclosed thief is captured. Against the others it hands them a
                # survival we then cannot reach into: stop one door short.
                if walled.is_enclosed(thief) and not view.claim_enclosure:
                    continue
                reach = len(bfs_distances(walled, thief))
                if reach < best_reach:
                    best_cell, best_reach = cell, reach
            if best_cell is not None and here_reach - best_reach >= self.seal_gain:
                return Decision(move="STAY", barrier=best_cell)

        return self._pick_move(view)

    def _pick_move(self, view: BrainView) -> Decision:
        moves = view.board.legal_moves(view.own_pos)
        thief = self.quarry(view)
        if thief is None:
            return Decision(move=view.rng.choice(moves))
        theirs = bfs_distances(view.board, thief)

        def score(move: str) -> tuple:
            pos = target_of(view.own_pos, move)
            # Landing on the thief ends it now; nothing else compares. Then
            # close, and let the room the step takes away break the ties - which
            # is the half of "take the ground" that a police step can actually
            # move. Room cannot lead: see the class docstring.
            gap = theirs.get(pos, FAR)
            room = self._room(view.board, thief, pos, theirs)
            return (pos != thief, gap, room, view.rng.random())

        return Decision(move=min(moves, key=score))
