"""Sparring partners: the policies other teams plausibly shipped.

None of these is meant to be strong. They are meant to be *different* - a
doctrine tuned against one evader learns that evader, which is exactly how the
90-98% self-play capture rate coexisted with 0/5 on the wire. Each brain here
is a plain reading of the book that a competent team could have written in an
afternoon, so a doctrine that scores well against all of them is answering a
family of opponents rather than a single fixed point.
"""

from __future__ import annotations

from ..domain.board import Cell, target_of
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
        quarry = self._quarry(view)
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
