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
"""

from __future__ import annotations

from collections import deque

from ..domain.board import Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.hints import region_of
from ..domain.rules import Decision
from .params import Doctrine, active
from .pathing import bfs_distances, still_connected
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
# squeezing, and it is knife-edge: 2 -> 6%, 3 -> 76%, 4 -> 92%, 5 -> 26%.

OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "northeast": "southwest", "southwest": "northeast",
            "northwest": "southeast", "southeast": "northwest", "center": "north"}
REVERSE = {"N": "S", "S": "N", "E": "W", "W": "E"}


class PoliceBrain(BrainBase):
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

    def _decide_move(self, view: BrainView) -> Decision:
        if view.sub_game != self._sub_game or view.step <= 1:
            self._sub_game, self._prev_fresh, self._fresh = view.sub_game, None, None
            self._last_move, self._camped = None, 0
            self._recent.clear()
            self._gaps.clear()
        # Track the scent trail on EVERY turn, including barrier turns: tracking
        # it inside the interception branch meant one barrier placement blinded
        # the velocity estimate for the turn after it (displacement of 2).
        self._track_trail(view)
        peak = view.belief.argmax()
        b_max = view.belief.grid[peak[0]][peak[1]]
        barrier = self._barrier_play(view, peak, b_max)
        # The squeeze (book 3.4): once the evader is on cramped ground, take its
        # exits one at a time. Enclosure - no legal move left - captures just as
        # landing on it does, and costs only 2 barriers in a corner.
        quarry = self._fresh or peak
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
        if barrier is not None:
            self._last_move = None
            return Decision(move="STAY", barrier=barrier)
        target = squeeze_target(view.board, view.own_pos, quarry) if evading else None
        return self._pursue(view, target or self._intercept_target(view) or peak)

    def _evading(self, view: BrainView, quarry: Cell) -> bool:
        """Has the gap stopped closing? Then distance alone will not finish this."""
        gap = bfs_distances(view.board, view.own_pos).get(quarry, 99)
        self._gaps.append(gap)
        return len(self._gaps) == self._gaps.maxlen and gap >= self._gaps[0]

    def _track_trail(self, view: BrainView) -> None:
        """Remember the freshest served-scent cell, turn over turn."""
        scent = view.opp_scent
        top = max(max(row) for row in scent)
        fresh = None
        if top >= self.p.police_fresh_min:  # only a genuinely fresh trail testifies
            fresh = max(((r, c) for r in range(view.board.size)
                         for c in range(view.board.size)),
                        key=lambda cell: scent[cell[0]][cell[1]])
        self._prev_fresh, self._fresh = self._fresh, fresh

    def _intercept_target(self, view: BrainView) -> Cell | None:
        """Solve the pursuit curve: meet the thief along its scent-trail velocity.

        The freshest served-scent cell marks where the thief *was*; its
        displacement between reveals is the thief's velocity - a cleaner
        signal than belief-peak jitter. Project position(t) = fresh + v*(1+k)
        and aim at the first projected cell we can reach in time.
        """
        fresh, prev = self._fresh, self._prev_fresh
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
        # Compare against the window BEFORE this turn joins it, so the test is
        # "has the posterior just sharpened relative to recent history".
        reference = max(self._recent) if self._recent else b_max
        self._recent.append(b_max)
        sharp = max(self.p.belief_floor, self.p.kill_shot_ratio * reference)
        adjacent_open = [c for c in view.board.neighbors4(view.own_pos) if view.board.is_open(c)]
        # Kill shot: our sharpest posterior sits on a cell we can bar now (#46).
        if b_max >= sharp and target in adjacent_open:
            return target
        if left <= self.p.endgame_reserve:
            return None
        # Corner seal: cornered belief mass close by - pinch its exit.
        if b_max >= max(self.p.belief_floor, self.p.seal_ratio * reference):
            dist = bfs_distances(view.board, view.own_pos)
            if dist.get(target, 99) <= self.p.seal_distance and self._is_cornered(view, target):
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

        def score(move: str) -> tuple:
            pos = target_of(view.own_pos, move)
            d = dist_from_target.get(pos, 9999)
            # Breaking ties against reversing damps the A->B->A dithering the
            # jittering belief peak induces (28% of moves were step-backs).
            reversing = 1 if move == REVERSE.get(self._last_move or "") else 0
            near = view.belief.mass_in({
                (pos[0] + dr, pos[1] + dc) for dr in (-2, -1, 0, 1, 2) for dc in (-2, -1, 0, 1, 2)
            })
            return (d, reversing, -near, view.rng.random())

        # Ambush is legitimate; camping is not. One STAY can pay - an evader may
        # walk onto us, which is how a random walker is often caught - but a
        # SECOND consecutive one is the pathology that idled 21% of all turns,
        # because standing on the peak makes STAY unbeatable on distance alone.
        moves = list(view.board.legal_moves(view.own_pos))
        if self._last_move == "STAY":
            moves = [m for m in moves if m != "STAY"] or moves
        best = min(moves, key=score)
        self._last_move = best
        return Decision(move=best)

    def _next_best_cell(self, view: BrainView) -> Cell | None:
        """Where to step when the peak is under our own feet.

        The neighbouring cell with the most belief mass around it - NOT the
        globally second-best cell, which can sit across the board and abandons
        the probability cloud altogether (measurably worse against an evader
        that diffuses rather than flees).
        """
        def local_mass(cell: Cell) -> float:
            return view.belief.mass_in({
                (cell[0] + dr, cell[1] + dc)
                for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            })

        best, best_mass = None, -1.0
        for cell in view.board.neighbors4(view.own_pos):
            if view.board.is_open(cell) and local_mass(cell) > best_mass:
                best, best_mass = cell, local_mass(cell)
        return best

    def should_claim(self, view: BrainView, new_pos: Cell) -> bool:
        belief_here = view.belief.grid[new_pos[0]][new_pos[1]]
        desperate = view.steps_remaining <= 8 and belief_here >= 0.05
        return belief_here >= self.claim_threshold or desperate

    def hint_plan(self, view: BrainView, decision: Decision) -> tuple[str, str]:
        """Herding lie: claim to close in from the opposite side of our true region."""
        if view.rng.random() < self.p.police_truth_rate:
            return region_of(view.own_pos, view.board.size), "truth"
        true_region = region_of(view.own_pos, view.board.size)
        return OPPOSITE.get(true_region, "north"), "lie"
