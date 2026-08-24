"""Police doctrine v4 (STRATEGY.md 6): lead pursuit, ambush discipline, rare barriers.

v3 kept velocity-lead interception off the scent trail and a disciplined claim
policy (a claim leaks our exact cell, so claims cost information). v4 fixes
three defects that instrumenting real games exposed:

* **Camping.** Standing on the belief argmax scored distance 0, so STAY was
  unbeatable and 21% of all police turns were spent frozen while the thief ran.
  One ambush turn is worth having - a random walker often walks onto us - so the
  rule is ambush once, then always step back onto the cloud.
* **Dithering.** 28% of real moves were A->B->A step-backs as the argmax
  jittered; reversing is now a tie-break penalty.
* **A dead threshold.** The kill shot required belief 0.30 while the measured
  posterior peak never exceeded 0.294, so rule #46 never once fired. Thresholds
  are now relative to a rolling window of recent peaks, which also self-calibrates
  to an opponent whose scent model - and so whose posterior scale - differs.

v5 adds the doctrine the book calls "the heart of the police's strategic
challenge" (3.4) and which v4 had measured its way out of: **the squeeze**. The
book names a third capture path - a thief with no legal move left is captured -
which costs only two barriers in a corner, where landing on a moving equal-speed
evader is near-impossible. `squeeze.py` closes its exits one at a time; this
module decides *when*, and the answer is "once the gap has stopped closing".
Against something that does not actually flee - a random walker - chasing still
wins outright, and spending those turns on doors cost 25/30 -> 20/30.

Barriers are otherwise still rare: an unconditional spend was measured and it
loses (see `belief_floor`). Every placement passes the flood-fill self-trap veto.

v6 is the first version to know where the thief *is*. Everything above reasons
about a belief cloud and a "freshest scent cell", and mining the played archive
showed both were far weaker than assumed: the served field saturates, so its
argmax names the emitter 11% of the time, and the shipped doctrine had pushed
`police_fresh_min` to 0.849 - above the 0.81 ceiling `book_v1` can serve - which
switched the trail branch off entirely (0 firings in 2,629 lab turns).
:mod:`..domain.tracking` replaces both by inverting the field, which is exact.

That turns the police's problem from *finding* the thief into *converting*, and
the archive is blunt about the conversion: 76 turns began with the thief one
step away and 11 of them ended on its cell. Twenty-seven were spent placing a
barrier instead - forfeiting the move, from a cell adjacent to the thief. So the
order of business is now pounce, then squeeze, then barrier, then pursue, and
pursuit aims at where the thief will be rather than where it was.

v7 is one division, and it is the only reason the league table reads the way it
does. `_pursue` scores a cell as ``d - w_cut * cut``. `d` is the distance to the
quarry and spans 0..12 on this board; `cut` was a raw count of cells we reach no
later than the thief and spans 0..49. The searched weight was 0.96, so a cell of
territory outscored a step of pursuit twelve times over - and the cell that owns
the most territory is the middle of the board. The doctrine that came out of the
search was therefore *stand in the middle of the board*, which every sparring
partner in the pool rewarded with a 100% capture rate because every one of them
eventually walks into a stationary pursuer.

Two teams did not. Replaying the sealed C001 archive through the raw term
reproduces the police's play move for move: it predicts STAY on 54 of 102 turns,
and the police played STAY on 54 of 102 turns - 48 with no barrier to show for
it - while the gap sat at 2 and 3 for whole sub-games. 0 captures in 6 counted
police sub-games across two matches, and 90 points, which is both losses.
Dividing `cut` by the board area makes it the tie-break the docstring always
said it was: the same term now predicts STAY on none of those 102 turns and
closes the gap on all of them.

The lab could not have found this, so `learn.opponents.Evader` was added to make
it findable: an evader that inverts our published field and refuses any cell the
pursuer can reach in one. Against the shipped police it survives 40 of 40, which
is the live result; against the fixed one, roughly three in four. Two things were
tried on top and measured *worse* over 200 seeds, so neither shipped: a safe-set
endgame that overrode the pursuit at close range (25.5% -> 23.0% at range 3 and
21.0% at range 5, monotone in how often it fired), and every barrier variant in
`test_police_pursuit`.

v8 finishes the conversion story v6 opened, by replaying the archive through
this brain instead of quoting what the archive's *own* doctrine did. The played
14% is history: today's brain converts 26 of the same 76 chances, and both
pathologies the review named are at zero - 27 turns spent barring from a cell
adjacent to the thief became 0, and 15 spent standing still became 0.

What remained was that `pounce_floor` gates an early return, so a chance below
it is discarded rather than discounted, and the floor cannot be lowered to
recover it: doing so stops `_pursue` running at all and the lab's capture rate
falls 0.812 -> 0.567 while the archive converts nothing extra until 0.10, by
which point it has already given up twenty points of capture. `w_pounce` prices
the same evidence as a term in the pursuit score instead, which takes the
archive to 29 of 76 and won every one of the five seed sets it was scored on.

Three other candidates were measured here and rejected, which is why they are
named rather than left to be re-proposed. `flee_bias` really is miscalibrated -
fitted to the played archive it is 1.05, and the 2.76 we ship is what the
reference kit's own bot fits, while every real team fits 1.00-1.15 - but the
fitted value converts no extra chance and costs nine points of lab capture
(0.812 -> 0.725), so the weight is doing a pursuit job, not a forecasting one.
Turning the kill shot into a step onto the same cell (rule #21 is honoured by
everyone, #46 is not) measured worse and, on inspection, never fired: the
belief-gated branches cannot be judged from an archive replay at all, because
the replay has no belief to feed them. And a barrier on the police's own cell -
which `validate` permits and `safe_decision` does not catch - occurs 0 times in
15,818 lab turns, because `still_connected` vetoes it from a source cell it has
just barred.
"""

from __future__ import annotations

from collections import deque

from ..domain.board import Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.hints import region_of
from ..domain.rules import Decision
from .mixing import choose
from .params import Doctrine, active
from .pathing import bfs_distances
from .police_barrier import PoliceBarrier
from .police_tracking import PoliceTracking
from .squeeze import squeeze_play, squeeze_target

# The numbers live in params.Doctrine (so the offline search in learn/ can
# address them); the reasoning stays here, next to the code that spends it.
#
# `kill_shot_ratio` / `seal_ratio` are RELATIVE to the sharpest posterior seen
# recently in this sub-game, never absolute. Absolute constants were calibrated
# by eye against our own scent model and silently went dead: the old kill shot
# needed 0.30 while the measured posterior peak never exceeded 0.294 over 385
# turns, so the barrier-capture rule (#46) never fired once. A ratio
# self-calibrates to any opponent's scent model, whose scale we cannot know.
#
# The reference must be a ROLLING window (`peak_window`), not an all-time max:
# step 1's belief is a delta on the known start cell (b_max = 1.0), which pins
# an all-time maximum forever and reproduces the very dead-threshold bug this
# replaces. The window forgets the opening certainty and tracks the fog-of-war
# scale the game settles into.
#
# `belief_floor` is deliberately high, and measured rather than guessed. A
# placement forfeits the move, and the swept trade-off (STRATEGY.md v4) says
# tempo beats area on this board: at floor 0.10 the police placed 2.45
# barriers/game and captured 20%, while at every floor from 0.18 up it placed
# none and captured 45% - identical to a barriers-off control. An area-denial
# doctrine was implemented too, measured at zero effect, and removed. Barriers
# are therefore a rare, decisive kill shot only.
#
# `gap_window` is turns of no closure before we switch from chasing to
# squeezing, and it is knife-edge - but the edge is in a different place under
# each physics, and both readings below are against `evader`, the only sparring
# partner that can tell a pursuer from a camper:
#
#     subtractive   2 -> 0%   3 -> 0%   4 -> 0%   6 -> 31%   8 -> 29%
#     book_v1                 3 -> 13%                       8 ->  7%
#
# Under subtractive the fix is exact, so chasing works and switching to the
# squeeze early throws the sub-game away. Under book_v1 the fix lags a turn,
# chasing a stale cell never closes, and the squeeze is worth reaching sooner.
# The two doctrines therefore disagree on this key by design, and a search that
# is allowed to move it under one physics must not be copied to the other.
#
# It is also the key that made a re-search actively harmful. Searching the
# police half under subtractive after the v7 rescale returned `gap_window` 3 -
# worth 0% against `evader` - while gaining nothing on the pooled objective
# (14.493 against 14.619 on hold-out), because `evader` is one member in twenty
# and the other nineteen reward anything. That vector was measured and dropped;
# the shipped subtractive doctrine is unchanged. The same search under book_v1
# improved every measure and was adopted.

OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "northeast": "southwest", "southwest": "northeast",
            "northwest": "southeast", "southeast": "northwest", "center": "north"}
REVERSE = {"N": "S", "S": "N", "E": "W", "W": "E"}


class PoliceBrain(PoliceBarrier, PoliceTracking, BrainBase):
    #: Open neighbours we refuse to drop below when placing a barrier. Two is
    #: "can still choose", one is a corridor, zero is a tomb - and the pursuer
    #: is the side that must keep moving.
    OWN_EXITS_FLOOR = 2

    def __init__(self, doctrine: Doctrine | None = None) -> None:
        self.p = doctrine or active()
        self.claim_threshold = self.p.claim_threshold
        self._prev_fresh: Cell | None = None
        self._fresh: Cell | None = None
        self._sub_game: int | None = None
        self._last_move: str | None = None
        self._recent: deque[float] = deque(maxlen=self.p.peak_window)
        self._camped = 0
        self._gaps: deque[int] = deque(maxlen=self.p.gap_window)
        self._where: dict[Cell, float] = {}

    def _decide_move(self, view: BrainView) -> Decision:
        if view.sub_game != self._sub_game or view.step <= 1:
            self._sub_game, self._prev_fresh, self._fresh = view.sub_game, None, None
            self._last_move, self._camped = None, 0
            self._recent.clear()
            self._gaps.clear()
            self._where = {}
        # Track the scent trail on EVERY turn, including barrier turns: tracking
        # it inside the interception branch meant one barrier placement blinded
        # the velocity estimate for the turn after it (displacement of 2).
        self._track_trail(view)
        peak = view.belief.argmax()
        b_max = view.belief.grid[peak[0]][peak[1]]
        # Where the thief is *now*, given a fix on where it was. Computed once
        # and reused: the pounce spends it, the pursuit aims at it, and the
        # claim is answered against it.
        self._where = self._thief_now(view)
        # First refusal to the capture. A barrier forfeits the move, so any turn
        # that could have ended on the thief's cell and ended on a barrier
        # instead traded a capture for a wall - 27 times in the played archive,
        # more than twice as often as we actually converted.
        pounce = self._pounce(view)
        if pounce is not None:
            self._last_move = pounce.move
            self._camped = 0
            return pounce
        barrier = self._barrier_play(view, peak, b_max)
        # The squeeze (book 3.4): once the evader is on cramped ground, take its
        # exits one at a time. Enclosure - no legal move left - captures just as
        # landing on it does, and costs only 2 barriers in a corner.
        quarry = self._likeliest() or self._fresh or peak
        # Squeeze only against a quarry that is genuinely evading. If we are
        # still closing the gap, chasing wins outright - that is how a random
        # walker gets caught, and spending those turns on doors instead cost
        # 25/30 -> 20/30 against one. Barriers are for the opponent that
        # distance alone can never catch. Evaluated ONCE per turn: it advances
        # a rolling window, so calling it twice would halve the window.
        evading = self._evading(view, quarry)
        if barrier is None and evading:
            barrier = squeeze_play(view.board, view.own_pos, quarry,
                                   quota_left=view.barrier_quota - view.barriers_used,
                                   reserve=self.p.endgame_reserve,
                                   claim_enclosure=view.claim_enclosure)
        if barrier is not None and self._would_seal(view, barrier):
            # Sealing the last exit only wins if the opponent agrees an enclosed
            # thief is captured. Against one that does not, it builds a pocket we
            # cannot enter either and hands them survival. `squeeze_play` already
            # refuses - but the barrier can equally come from `_barrier_play`'s
            # corner seal, which had no such guard. Measured live 2026-08-01: we
            # barred (6,5) and (5,6), their thief sat in (6,6) for 23 turns, and
            # our police finished outside its own wall. 5 points where 20 was on
            # offer, in all six sub-games.
            barrier = None
        if barrier is not None:
            self._last_move = None
            return Decision(move="STAY", barrier=barrier)
        target = squeeze_target(view.board, view.own_pos, quarry) if evading else None
        return self._pursue(view, target or self._intercept_target(view)
                            or self._likeliest() or peak)

    def _pounce(self, view: BrainView) -> Decision | None:
        """Step onto the thief, when a step can reach it.

        This is the capture. Landing on the thief's cell and claiming it is
        answered truthfully by rule #21, which every peer in the league
        implements because the protocol does not work without it - unlike rule
        #46 (a barrier onto the thief), which several do not honour. So when a
        cell we can enter this turn is plausibly the thief's, entering it is
        strictly better than barring it: same evidence, same trigger, and the
        conversion path is the one that is actually agreed.
        """
        if not self._where:
            return None
        moves = view.board.legal_moves(view.own_pos)
        best, best_p = None, 0.0
        for move in moves:
            chance = self._where.get(target_of(view.own_pos, move), 0.0)
            if chance > best_p:
                best, best_p = move, chance
        if best is None or best_p < self.p.pounce_floor:
            return None
        return Decision(move=best)

    def _pursue(self, view: BrainView, target: Cell) -> Decision:
        # Standing on the belief peak is worth exactly ONE turn: an evader may
        # walk onto us, which is how a random walker is most often caught. From
        # the second turn it is a trap - distance-only scoring makes STAY
        # unbeatable there (d = 0), which idled 21% of all police turns while
        # the thief ran free. So: ambush once, then always retarget.
        if target == view.own_pos:
            if self._camped:
                target = self._next_best_cell(view) or target
            self._camped += 1
        else:
            self._camped = 0
        dist_from_target = bfs_distances(view.board, target)
        # Room the thief owns, from wherever it most likely is. Distance alone
        # is a tail chase between equal-speed agents - the evidence names where
        # it was, so aiming there holds the gap open forever. Taking ground it
        # would otherwise reach first is how the gap actually closes.
        quarry = self._likeliest()
        theirs = bfs_distances(view.board, quarry) if quarry is not None else {}
        far = view.board.size * view.board.size

        def score(move: str) -> tuple:
            pos = target_of(view.own_pos, move)
            d = dist_from_target.get(pos, 9999)
            # Breaking ties against reversing damps the A->B->A dithering the
            # jittering belief peak induces (28% of moves were step-backs).
            reversing = 1 if move == REVERSE.get(self._last_move or "") else 0
            near = view.belief.mass_in({
                (pos[0] + dr, pos[1] + dc) for dr in (-2, -1, 0, 1, 2) for dc in (-2, -1, 0, 1, 2)
            })
            # Territory is a FRACTION of the board, never a raw cell count, and
            # the difference decided the league. Counted raw, `cut` ranges over
            # 0..49 while `d` ranges over 0..12, so at the searched weight of
            # 0.96 one cell of territory outscored one step of pursuit twelve
            # times over - and the cell that owns the most board is the middle
            # of it. Replayed from the counted match against uoh-ay26, step 10,
            # police (3,3) and thief (2,4):
            #
            #     STAY  d=2 cut=40  ->  -36.38   <- chosen
            #     N     d=1 cut=28  ->  -25.87
            #
            # Closing the gap was worth 1 point and standing still was worth
            # 11.5, so the police stood still: 17 of 34 turns in that sub-game,
            # and 0 captures in 6 sub-games across two counted matches. The
            # search space for `w_cut` is (0, 2), which is only meaningful
            # against a normalised quantity; the raw count made the same number
            # mean "ignore the thief". Divided by the board area it is what the
            # docstring always claimed it was - a tie-break between equally
            # close cells, taking the one that also owns more ground.
            cut = 0.0
            if theirs:
                mine = bfs_distances(view.board, pos)
                cut = sum(1 for cell, theirs_d in theirs.items()
                          if mine.get(cell, far) <= theirs_d) / far
            # The capture chance the pounce declined, priced instead of
            # discarded. `_pounce` returns early, so its floor is an
            # all-or-nothing switch: below it a chance is thrown away entirely,
            # and lowering it does not take more shots so much as stop this
            # function running - measured, the archive converts no more chances
            # at floor 0.20 than at 0.262 while the lab's capture rate falls
            # 0.812 -> 0.704, and 0.567 by floor 0.04. Scored here it competes
            # with distance and territory on one scale, so a cell the tracker
            # says might hold the thief tilts a move without owning it.
            catch = self._where.get(pos, 0.0)
            return (d - self.p.w_cut * cut - self.p.w_pounce * catch,
                    reversing, -near, view.rng.random())

        # Ambush is legitimate; camping is not. One STAY can pay - an evader may
        # walk onto us, which is how a random walker is often caught - but a
        # SECOND consecutive one is the pathology that idled 21% of all turns,
        # because standing on the peak makes STAY unbeatable on distance alone.
        moves = list(view.board.legal_moves(view.own_pos))
        if self._last_move == "STAY":
            moves = [m for m in moves if m != "STAY"] or moves
        best = choose(moves, score, self.p.police_mix_margin, view.rng, prefer=min)
        self._last_move = best
        return Decision(move=best)

    def should_claim(self, view: BrainView, new_pos: Cell) -> bool:
        """Claim whenever the cell we just took is plausibly the thief's.

        The scent fix supersedes the belief here, and by a wide margin: the
        belief peak names the thief's cell 9% of the time in the lab, while a
        fix is exact. A claim does leak our own cell - but the opponent can read
        that off the field we are required to publish anyway, by the same
        inversion we use, so the leak is not information it was owed and did not
        have. What a missed claim costs is the capture itself.
        """
        if self._where.get(new_pos, 0.0) > 0.0:
            return True
        belief_here = view.belief.grid[new_pos[0]][new_pos[1]]
        desperate = view.steps_remaining <= 8 and belief_here >= 0.05
        return belief_here >= self.claim_threshold or desperate

    def hint_plan(self, view: BrainView, decision: Decision) -> tuple[str, str]:
        """Herding lie: claim to close in from the opposite side of our true region."""
        if view.rng.random() < self.p.police_truth_rate:
            return region_of(view.own_pos, view.board.size), "truth"
        true_region = region_of(view.own_pos, view.board.size)
        return OPPOSITE.get(true_region, "north"), "lie"
