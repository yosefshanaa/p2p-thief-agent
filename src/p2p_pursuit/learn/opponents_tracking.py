"""Archetypes that invert the served scent field to pin the emitter's cell.

Split out of :mod:`.opponents` (§3.2). `Interceptor` does to us what we do
to opponents; `Replayer` and `Sniper` specialise it."""

from __future__ import annotations

from ..domain.board import Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.rules import Decision
from ..strategy.pathing import bfs_distances
from .opponents_base import FAR, _manhattan, _step_toward


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
