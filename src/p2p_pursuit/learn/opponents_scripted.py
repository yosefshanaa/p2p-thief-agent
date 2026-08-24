"""Opponents replayed from a record rather than computed: a fixed script, a
full transcript, and the najamjad cage captured from live play.

Split out of :mod:`.opponents` (§3.2). A script is honest only for a
deterministic opponent; a transcript replays what a real team actually did."""

from __future__ import annotations

from ..domain.board import Cell
from ..domain.brains_base import BrainBase, BrainView
from ..domain.rules import Decision


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
#: The cage as it was played in the COUNTED series, 2026-08-21 - the version
#: that kills. Its predecessor (kept below) is the one from the friendlies the
#: same evening, and the difference between them is a single placement.
#:
#: Eleven of the twelve barriers are identical in both. The twelfth was `(0, 5)`
#: on turn 34, which seals nothing and let our thief run out the full 35 steps in
#: all six friendly windows; here it is `(1, 4)` on turn 30, which shuts the box
#: five moves inside the survival threshold and took all three counted windows.
#: Training against the old one measures a cage that cannot win.
NAJAMJAD_CAGE_MOVES: tuple[str, ...] = (
    "E", "E", "STAY", "S", "STAY", "S", "STAY", "S", "STAY", "S", "STAY", "S",
    "STAY", "S", "E", "E", "STAY", "N", "N", "STAY", "E", "STAY", "E", "N",
    "N", "STAY", "N", "W", "STAY", "STAY",
)
NAJAMJAD_CAGE_BARRIERS: tuple[Cell | None, ...] = (
    None, None, (0, 3), None, (1, 3), None, (2, 3), None, (3, 3), None,
    (4, 3), None, (5, 3), None, None, None, (6, 3), None, None, (3, 4),
    None, (3, 5), None, None, None, (3, 6), None, None, (2, 5), (1, 4),
)
#: The friendly-era cage, kept because the pair of them is the evidence that this
#: opponent iterates between meetings - and because a doctrine that survives the
#: harmless one has proved nothing.
NAJAMJAD_CAGE_MOVES_FRIENDLY: tuple[str, ...] = (
    "E", "E", "STAY", "S", "STAY", "S", "STAY", "S", "STAY", "S", "STAY", "S",
    "STAY", "S", "E", "E", "STAY", "N", "N", "STAY", "E", "STAY", "E", "N",
    "N", "STAY", "N", "W", "STAY", "W", "S", "N", "E", "STAY",
)
NAJAMJAD_CAGE_BARRIERS_FRIENDLY: tuple[Cell | None, ...] = (
    None, None, (0, 3), None, (1, 3), None, (2, 3), None, (3, 3), None,
    (4, 3), None, (5, 3), None, None, None, (6, 3), None, None, (3, 4),
    None, (3, 5), None, None, None, (3, 6), None, None, (2, 5), None,
    None, None, None, (0, 5),
)


def najamjad_cage() -> Transcript:
    """The cage exactly as it was played in the counted series - the lethal one."""
    return Transcript(NAJAMJAD_CAGE_MOVES, NAJAMJAD_CAGE_BARRIERS)
