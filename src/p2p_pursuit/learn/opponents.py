"""Sparring partners: the policies other teams plausibly shipped.

None of these is meant to be strong. They are meant to be *different* - a
doctrine tuned against one evader learns that evader, which is exactly how the
90-98% self-play capture rate coexisted with 0/5 on the wire. Each brain here
is a plain reading of the book that a competent team could have written in an
afternoon, so a doctrine that scores well against all of them is answering a
family of opponents rather than a single fixed point.
"""

from __future__ import annotations

from ..domain.board import target_of
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
