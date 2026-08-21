"""Sparring partners: the policies other teams plausibly shipped.

None of these is meant to be strong. They are meant to be *different* - a
doctrine tuned against one evader learns that evader, which is exactly how the
90-98% self-play capture rate coexisted with 0/5 on the wire. Each brain here
is a plain reading of the book that a competent team could have written in an
afternoon, so a doctrine that scores well against all of them is answering a
family of opponents rather than a single fixed point.
"""

from __future__ import annotations

from ..domain.board import Board, Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.rules import Decision
from ..strategy.pathing import bfs_distances

FAR = 99


class RandomWalker(BrainBase):
    """Uniform over legal moves. The floor every doctrine must beat."""

    def _pick_move(self, view: BrainView) -> Decision:
        return Decision(move=view.rng.choice(view.board.legal_moves(view.own_pos)))


class Momentum(BrainBase):
    """Holds a heading until it is blocked, then picks a new one.

    Straight-line flight is the most common naive evasion, and the reference
    peer's opening moves in our warm-up match looked exactly like it.
    """

    def __init__(self, turn_rate: float = 0.25) -> None:
        self.turn_rate = turn_rate
        self._heading: str | None = None

    def _pick_move(self, view: BrainView) -> Decision:
        moves = [m for m in view.board.legal_moves(view.own_pos) if m != "STAY"]
        if not moves:
            return Decision(move="STAY")
        if self._heading not in moves or view.rng.random() < self.turn_rate:
            self._heading = view.rng.choice(moves)
        return Decision(move=self._heading)


class Greedy(BrainBase):
    """Walk down (or up) the distance gradient to the opponent's likely cell.

    The obvious implementation, and therefore the one to expect most often:
    ``flee`` inverts it for a thief, ``use_trail`` reads the pheromone trail
    instead of the posterior, and ``jitter`` is the epsilon a team adds once it
    notices a pure gradient is trivially predictable.
    """

    def __init__(self, *, flee: bool, use_trail: bool = False, jitter: float = 0.0) -> None:
        self.flee, self.use_trail, self.jitter = flee, use_trail, jitter

    def target(self, view: BrainView) -> tuple[int, int]:
        if self.use_trail:
            top = max(max(row) for row in view.opp_scent)
            if top > 0.0:
                size = view.board.size
                return max(((r, c) for r in range(size) for c in range(size)),
                           key=lambda cell: view.opp_scent[cell[0]][cell[1]])
        return view.belief.argmax()

    def _pick_move(self, view: BrainView) -> Decision:
        moves = view.board.legal_moves(view.own_pos)
        if self.jitter and view.rng.random() < self.jitter:
            return Decision(move=view.rng.choice(moves))
        dist = bfs_distances(view.board, self.target(view))
        sign = -1 if self.flee else 1

        def key(move: str) -> tuple[float, float]:
            return (sign * dist.get(target_of(view.own_pos, move), FAR), view.rng.random())

        return Decision(move=min(moves, key=key))


class BarrierHappy(Greedy):
    """A police that spends its quota freely - the doctrine we measured *out* of.

    Worth keeping in the pool precisely because we rejected it: our thief has
    never been tested against an opponent that walls the board in, and the book
    grants 14 barriers on 49 cells, so somebody will play this.
    """

    def __init__(self, floor: float = 0.08) -> None:
        super().__init__(flee=False)
        self.floor = floor

    def _decide_move(self, view: BrainView) -> Decision:
        peak = view.belief.argmax()
        left = view.barrier_quota - view.barriers_used
        open_adjacent = [c for c in view.board.neighbors4(view.own_pos) if view.board.is_open(c)]
        if left > 0 and peak in open_adjacent and view.belief.grid[peak[0]][peak[1]] >= self.floor:
            return Decision(move="STAY", barrier=peak)
        return self._pick_move(view)


class Holder(BrainBase):
    """An evader that keeps room around it instead of maximising distance.

    Distance-maximising evaders walk into corners, which is the whole reason
    the squeeze works. This one weighs mobility against distance, so it is the
    pool member that punishes a police relying on enclosure.
    """

    def __init__(self, w_mobility: float = 1.5) -> None:
        self.w_mobility = w_mobility

    def _pick_move(self, view: BrainView) -> Decision:
        dist = bfs_distances(view.board, view.belief.argmax())

        def score(move: str) -> float:
            pos = target_of(view.own_pos, move)
            room = len(view.board.open_neighbors(pos))
            return (dist.get(pos, FAR) + self.w_mobility * room
                    - (1.0 if move == "STAY" else 0.0) + view.rng.random() * 1e-3)

        return Decision(move=max(view.board.legal_moves(view.own_pos), key=score))


class Camper(BrainBase):
    """Runs for the nearest corner, then stops moving.

    Not invented for variety - this is what the reference peer's thief actually
    did in a live match: it reached (6,6) and sat there for 27 consecutive
    turns while our police walled it in and never stepped on it. Measured
    2026-08-01, six sub-games, zero captures.

    It is the cheapest possible evader and it beat our best police, because a
    pursuer that plays for enclosure against an opponent who does not honour
    enclosure converts nothing. Nothing else in the pool behaves this way:
    `holder` deliberately preserves mobility, which is the opposite instinct.
    """

    def __init__(self, settle_after: int = 8) -> None:
        self.settle_after = settle_after
        self._corner: Cell | None = None

    def _pick_move(self, view: BrainView) -> Decision:
        size = view.board.size
        if self._corner is None:
            corners = [(0, 0), (0, size - 1), (size - 1, 0), (size - 1, size - 1)]
            here = view.own_pos
            self._corner = min(corners,
                               key=lambda c: abs(c[0] - here[0]) + abs(c[1] - here[1]))
        if view.own_pos == self._corner:
            return Decision(move="STAY")
        dist = bfs_distances(view.board, self._corner)
        return Decision(move=min(view.board.legal_moves(view.own_pos),
                                 key=lambda m: (dist.get(target_of(view.own_pos, m), FAR),
                                                view.rng.random())))


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


class Interceptor(BrainBase):
    """A police that inverts the scent field, as we now do - the one to fear.

    Every other police in this pool navigates by belief or by the field's
    argmax, and against all of them our thief survives: in the search that
    produced v8's thief half, sixteen of seventeen pool members scored a flat
    10.00, which is another way of saying the objective could not see the thief
    at all. An optimiser tunes only what its objective can punish, and that one
    duly drove `corner_penalty` to 0.001 - it had never been shown a pursuer
    that could exploit a corner.

    Nothing here is speculative. The inversion is arithmetic over a field the
    rules require both peers to publish, so any team that notices can do it, and
    a doctrine that only survives opponents who have *not* noticed is a doctrine
    with an expiry date. This is that team, written out: chase the exact cell,
    step onto it when a step reaches it, and spend barriers on the exits of a
    thief that has run out of room.

    It reads `view.opp_cells`, so it is only as strong as the fix - against a
    peer serving no scent at all it degrades to the belief peak, like everything
    else.
    """

    #: How much a candidate move's cut of the thief's ground is worth against a
    #: step of raw closing distance. Chasing alone does not work and that is the
    #: point of this archetype: measured, a pursuer that knows the thief's exact
    #: cell and simply walks toward it catches our evader **0 times in 12** - two
    #: equal-speed agents on open ground never meet. Captures come from taking
    #: the room away, so that is what this one spends its move on.
    CUT_WEIGHT = 0.6

    def __init__(self, *, squeeze_within: int = 3) -> None:
        self.squeeze_within = squeeze_within

    def _quarry(self, view: BrainView) -> Cell:
        return view.opp_fix if view.opp_fix is not None else view.belief.argmax()

    def _decide_move(self, view: BrainView) -> Decision:
        quarry = self._quarry(view)
        here = view.own_pos
        reach = [c for c in view.board.neighbors4(here) if view.board.is_open(c)]
        # Certain capture beats everything else on the board.
        if quarry in reach and len(view.opp_cells) == 1:
            return Decision(move=_step_toward(here, quarry))
        left = view.barrier_quota - view.barriers_used
        theirs = bfs_distances(view.board, quarry)
        if left > 0 and theirs.get(here, FAR) <= self.squeeze_within:
            # Close its doors from the outside in: the exit that costs it the
            # most room, provided we can still get at it afterwards.
            exits = [c for c in view.board.neighbors4(quarry)
                     if view.board.is_open(c) and c in reach and c != here]
            if exits and len(view.board.open_neighbors(quarry)) > 1:
                def room(cell: Cell) -> int:
                    trial = view.board.clone()
                    trial.add_barrier(cell)
                    return len(bfs_distances(trial, quarry))

                return Decision(move="STAY", barrier=min(exits, key=room))
        return self._pick_move(view)

    def _pick_move(self, view: BrainView) -> Decision:
        return self._approach(view, self._quarry(view))

    def _approach(self, view: BrainView, quarry: Cell) -> Decision:
        """Close on ``quarry``, whichever cell the subclass decided that is."""
        theirs = bfs_distances(view.board, quarry)
        far = view.board.size * view.board.size

        def key(move: str) -> tuple[float, float]:
            pos = target_of(view.own_pos, move)
            if not view.board.is_open(pos):
                return (FAR, 0.0)
            mine = bfs_distances(view.board, pos)
            cut = sum(1 for cell, d in theirs.items() if mine.get(cell, far) <= d)
            return (theirs.get(pos, FAR) - self.CUT_WEIGHT * cut, view.rng.random())

        # A pursuer that stands still is not pursuing. The Voronoi term is not
        # monotone in distance - the middle of the board owns more cells than a
        # square nearer the thief does - so left free it picks STAY forever, and
        # camping is the same pathology our own police was measured out of.
        moves = [m for m in view.board.legal_moves(view.own_pos) if m != "STAY"]
        return Decision(move=min(moves or ["STAY"], key=key))


class Replayer(Interceptor):
    """A pursuer that remembers the last sub-game - so a fixed policy dies to it.

    Every other member of this pool meets our doctrine fresh, and that is the
    one thing a league opponent never does. A match is six sub-games from the
    same two starting cells under the same constitution, and both our brains are
    pure functions of the view: no sampling anywhere in either move rule. Feed
    the same evader a similar pursuer and it replays. Measured on the played
    uoh-ay26 friendly, our thief's last six moves were
    ``STAY / off / back / STAY / off / back`` around (5,5) in **all three** of
    its sub-games, and it was taken on (5,5) at step 10 all three times.

    So this archetype does what that team's police effectively did. It records
    the evader's cell at each step - by inverting the scent field, which is
    public, so nothing here is information a real opponent could not have - and
    in later sub-games aims at where the evader *will be* rather than where it
    is. The distinction is the whole archetype: :class:`Interceptor` documents
    that chasing an exactly-known evader catches it 0 times in 12, because two
    equal-speed agents on open ground never meet. Interception is not chasing.

    Against a policy with any real mixing in it the memory is worthless and this
    degrades to its parent. That asymmetry is the point - it is an exploitability
    probe, and the only pool member whose score answers "would a team that has
    already seen us beat us again".
    """

    #: How far ahead to look for a cell we can reach before the evader does.
    #: Six is the sub-game's own scale - our thief died on step 10 of 10 - and a
    #: longer horizon just re-finds the same trap through a noisier forecast.
    LEAD_CAP = 6

    def __init__(self, *, squeeze_within: int = 3) -> None:
        super().__init__(squeeze_within=squeeze_within)
        self._past: list[dict[int, Cell]] = []
        self._current: dict[int, Cell] = {}
        self._step = 0

    def _remember(self, view: BrainView) -> None:
        """File this turn's sighting, rolling the ledger at a sub-game boundary.

        The boundary is read off ``view.step`` rather than ``view.sub_game``: the
        lab builds a fresh engine per sub-game, so every one of them is sub-game
        1, and only the step counter restarting says a new one began.
        """
        if view.step <= self._step:
            if self._current:
                self._past.append(self._current)
            self._current = {}
        self._step = view.step
        if view.opp_fix is not None:
            self._current[view.step] = view.opp_fix

    def _forecast(self, view: BrainView) -> Cell | None:
        """The soonest future cell of the evader's replay that we can reach first.

        Earliest rather than nearest: a later interception point is one the
        evader has more chances to deviate from, and on a board this size the
        first reachable point is almost always the trap it walks into anyway.
        """
        if not self._past:
            return None
        mine = bfs_distances(view.board, view.own_pos)
        for lead in range(1, self.LEAD_CAP + 1):
            step = view.step + lead
            seen = [run[step] for run in self._past if step in run]
            if not seen:
                continue
            cell = max(set(seen), key=seen.count)
            if view.board.is_open(cell) and mine.get(cell, FAR) <= lead:
                return cell
        # Nothing is reachable in time, so head for where it ended up last time
        # and be standing there when it arrives.
        last = self._past[-1]
        cell = last[max(last)]
        return cell if view.board.is_open(cell) else None

    def _decide_move(self, view: BrainView) -> Decision:
        self._remember(view)
        ambush = self._ambush(view)
        return ambush or super()._decide_move(view)

    def _ambush(self, view: BrainView) -> Decision | None:
        """Wall the trap cell in *before* the evader walks into it.

        This is the half that converts. :class:`Interceptor` records that simply
        knowing the evader's cell catches it 0 times in 12, because two agents of
        equal speed on open ground never meet - captures come from taking the
        room away. Standing on the forecast cell is not enough either: the evader
        just goes somewhere else. Sealing that cell's exits while we stand on one
        of them is what makes the prediction pay, and it is only available to a
        pursuer that knows where the evader is *going*.
        """
        target = self._forecast(view)
        left = view.barrier_quota - view.barriers_used
        if target is None or left <= 0 or target == view.own_pos:
            return None
        if _manhattan(view.own_pos, target) > 1:
            return None
        quarry = self._quarry(view)
        if _manhattan(quarry, target) <= 1:
            return None  # it is already here; play it out rather than build
        exits = [c for c in view.board.neighbors4(target)
                 if view.board.is_open(c) and c != view.own_pos]
        if len(exits) <= 1:
            return None  # one door left is a pocket we still want it to enter
        theirs = bfs_distances(view.board, quarry)
        return Decision(move="STAY", barrier=min(exits, key=lambda c: theirs.get(c, FAR)))

    def _pick_move(self, view: BrainView) -> Decision:
        # The capture and barrier branches upstairs still read the *true* cell;
        # only the navigation target is the forecast. Ambushing a cell we could
        # have stepped onto this turn would be a worse pursuer, not a better one.
        return self._approach(view, self._forecast(view) or self._quarry(view))


class Sniper(Interceptor):
    """Bars the cell the evader is *standing on*. This is how we actually die.

    Mined from every sub-game on file, our thief has been taken 54 times by a
    real opponent, and the ending was:

        31  barrier onto (r,c)   - a barrier placed on the cell we occupied
        16  enclosed             - sealed into a pocket
         7  a pursuer stepped onto us

    So 87% of our deaths are barrier kills and the pool models none of them.
    `barrier` (BarrierHappy) bars the *belief peak*, which the archive measures
    1.85 cells off and exact 26% of the time, so it lands on the evader almost
    never; `interceptor` and `replayer` deliberately bar exits and never the
    quarry itself. The consequence is an objective that reported 100% thief
    survival while the real league was converting us at 61%, and a search that
    duly drove `corner_penalty` toward nothing because no pool member could
    punish a corner.

    Nothing here is exotic - it is the shortest path from the scent fix that we
    ourselves already have. Invert the published field, and if the evader is
    standing next to you, spend a barrier on the cell it is standing on. Rule
    #46 and the placement rule ("own or orthogonally adjacent") allow exactly
    that, and orcai-mj played it 25 times against us in one match.

    Against an evader that never lets a pursuer stand adjacent, this archetype
    is harmless. That is the lesson it is in the pool to teach.
    """

    def _decide_move(self, view: BrainView) -> Decision:
        quarry = self._quarry(view)
        left = view.barrier_quota - view.barriers_used
        # Gated on having a FIX, not on the fix being current. Requiring
        # `len(opp_cells) == 1` made this archetype inert under every lag-1
        # model - `book_v1` serves before it emits, so no opponent can ever know
        # our cell exactly under it, and the member silently degraded to its
        # parent in exactly the physics we play by default. A one-step-old fix
        # is still a real threat: it bars the cell we were standing on, which
        # takes us if we stayed. Barring the diffuse *belief* peak is the
        # measured pathology of `barrier` and remains excluded.
        if (left > 0 and view.opp_fix is not None and view.board.is_open(quarry)
                and quarry in view.board.neighbors4(view.own_pos)):
            return Decision(move="STAY", barrier=quarry)
        return super()._decide_move(view)


def _manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(here: Cell, there: Cell) -> str:
    if there[0] < here[0]:
        return "N"
    if there[0] > here[0]:
        return "S"
    return "E" if there[1] > here[1] else "W"


class Scripted(BrainBase):
    """Replays one recorded move sequence, in order, every sub-game.

    Every other member of this pool is a *policy*: give it a board and it
    reasons. This one is a transcript. It exists because a fitted clone answers
    the wrong question against a deterministic opponent - gal-roy1's thief walks
    an identical perimeter loop in every sub-game, and their clone, fitted at 78%
    move agreement, is a reactive imitation that wanders where the original never
    does. Our shipped doctrine catches that imitation 83% of the time in
    simulation while catching the original 0 times in 9 live sub-games, so the
    imitation cannot be what we tune against.

    ``view.step`` indexes the script, so the replay restarts with each sub-game
    without this brain tracking any state of its own.

    One honest limitation, because it bounds what a capture here is worth: when
    our barriers make the scripted move illegal, the transcript has nothing to
    say and this brain holds position. A live thief would deviate and might
    escape, so a capture that depends on blocking the loop is evidence the seal
    works, not proof the opponent cannot answer it.
    """

    def __init__(self, moves: tuple[str, ...]) -> None:
        if not moves:
            raise ValueError("a scripted opponent needs at least one move")
        self.moves = moves

    def _pick_move(self, view: BrainView) -> Decision:
        move = self.moves[(max(view.step, 1) - 1) % len(self.moves)]
        if move != "STAY" and move not in view.board.legal_moves(view.own_pos):
            return Decision(move="STAY")
        return Decision(move=move)


class Transcript(BrainBase):
    """Replays a recorded police transcript - moves **and** barrier placements.

    :class:`Scripted` replays a move sequence, which is enough for an evader but
    not for a pursuer whose whole strategy is where it spends its quota. The
    cage that took our thief is built out of barriers on specific turns; drop
    them and the same walk is a police that wanders past us.

    Built for najamjad's police, 2026-08-20, which played **move-for-move and
    barrier-for-barrier identically in all three of its windows** - so a
    transcript is not a lossy summary of that opponent, it is the opponent. It
    walks south down column 2 walling column 3 on alternate turns, then turns
    the top-right corner into a seven-cell pocket and steps inside it.

    The same honest limitation as :class:`Scripted`, and it bites harder here:
    when the script's move is illegal or its barrier cell is already taken, the
    transcript has nothing to say and we hold. A live cager would re-plan. So a
    thief that survives this has survived *this* cage, not caging - which is
    exactly the distinction our archive says we keep getting wrong.
    """

    def __init__(self, moves: tuple[str, ...],
                 barriers: tuple[Cell | None, ...] = ()) -> None:
        if not moves:
            raise ValueError("a transcript needs at least one turn")
        if barriers and len(barriers) != len(moves):
            raise ValueError("moves and barriers must line up turn for turn")
        self.moves = moves
        self.barriers = barriers or (None,) * len(moves)

    def _decide_move(self, view: BrainView) -> Decision:
        i = (max(view.step, 1) - 1) % len(self.moves)
        barrier = self.barriers[i]
        if (barrier is not None
                and view.barriers_used < view.barrier_quota
                and view.board.is_open(barrier)
                and barrier != view.own_pos):
            # Placing forfeits the move, which is what the original did too.
            return Decision(move="STAY", barrier=barrier)
        move = self.moves[i]
        if move != "STAY" and move not in view.board.legal_moves(view.own_pos):
            return Decision(move="STAY")
        return Decision(move=move)


#: najamjad's police, 2026-08-20, lifted from `opponent_records` of g02/g04/g06
#: (all three identical). Their cage is the only one in our archive that sealed
#: our thief into a genuinely small pocket - 49 cells down to 7 - so it is the
#: only real evidence we have of the failure mode `Cager` was written to model.
NAJAMJAD_CAGE_MOVES: tuple[str, ...] = (
    "E", "E", "STAY", "S", "STAY", "S", "STAY", "S", "STAY", "S", "STAY", "S",
    "STAY", "S", "E", "E", "STAY", "N", "N", "STAY", "E", "STAY", "E", "N",
    "N", "STAY", "N", "W", "STAY", "W", "S", "N", "E", "STAY",
)
NAJAMJAD_CAGE_BARRIERS: tuple[Cell | None, ...] = (
    None, None, (0, 3), None, (1, 3), None, (2, 3), None, (3, 3), None,
    (4, 3), None, (5, 3), None, None, None, (6, 3), None, None, (3, 4),
    None, (3, 5), None, None, None, (3, 6), None, None, (2, 5), None,
    None, None, None, (0, 5),
)


def najamjad_cage() -> Transcript:
    """The cage exactly as it was played, for the thief search to train against."""
    return Transcript(NAJAMJAD_CAGE_MOVES, NAJAMJAD_CAGE_BARRIERS)
