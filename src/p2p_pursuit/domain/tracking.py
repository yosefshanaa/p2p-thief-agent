"""Track the opponent by inverting its served scent field, turn over turn.

:mod:`.scent_locate` answers "which cell emitted between these two fields"; this
keeps the running state that makes the answer usable during a game - the field
we saw last turn, the fix we took from it, and the fix before that, which is a
*velocity*.

Three things it is careful about, each of which was a defect in the estimator it
replaces:

* **Continuity.** After the first fix the scan is restricted to the cells the
  emitter could physically have reached. That is the cheap path (5 replays
  instead of 49) and it is also the check: a candidate that cannot be reached
  from the last fix is not a better explanation of the field, it is noise.
* **Lag.** ``book_v1`` serves before emitting, so its fix is one step old; the
  other two models serve after, so theirs is current. :attr:`possible` folds
  that in and answers the only question a brain actually has - which cells could
  the opponent be standing on *now*.
* **Silence.** A repeated field (a turn arrived without an intervening opponent
  step) carries no new evidence, and a fix that cannot be pinned uniquely is
  reported as no fix at all. Both leave the previous belief standing rather than
  replacing it with a guess.
"""

from __future__ import annotations

from .board import Board, Cell
from .scent import BOOK_V1, SUBTRACTIVE_V1
from .scent_locate import changed, fix_lag, locate_emitter

#: Models whose served field's ``argmax`` already IS the emitter's cell, so
#: inverting adds nothing and costs coverage.
#:
#: `subtractive_chebyshev_v1` merges emission by **max** and decays by
#: subtraction, so the freshest cell stands alone at the ceiling and the peak is
#: exact - while that same max-merge makes an emitter that STAYS produce a
#: transition no centre uniquely explains, which the inverse correctly reports
#: as "no fix". Measured on the played uoh-ay26 friendly: the inverse was right
#: 93 times, silent 33, and wrong never - and all 33 silences were the opponent
#: standing still, where the argmax was right every time. 74% against 100%, for
#: information that was already free.
#:
#: The additive models are the opposite case and the reason the inverse exists:
#: emission adds and clamps, a whole region pins at the cap, and `book_v1`'s
#: argmax is right 1 time in 9.
ARGMAX_IS_EXACT = frozenset({SUBTRACTIVE_V1})

Field = list[list[float]]


class OpponentTracker:
    """Where the opponent is, read off the field it is required to publish."""

    def __init__(self, size: int, model: str = BOOK_V1) -> None:
        self.size = size
        self.model = model
        self.lag = fix_lag(model)
        self.fix: Cell | None = None
        self.previous_fix: Cell | None = None
        self.fixes = 0
        self._last_field: Field | None = None

    def observe(self, scent: Field, board: Board) -> Cell | None:
        """Fold in one freshly served field; returns the new fix, if there is one."""
        if not scent or not any(any(row) for row in scent):
            return None
        previous, self._last_field = self._last_field, [row[:] for row in scent]
        if self.model in ARGMAX_IS_EXACT:
            # Deliberately BEFORE the changed() gate. That gate exists because a
            # transition is the evidence the inverse consumes, so an unchanged
            # field carries none. The argmax consumes the field itself, and an
            # emitter that stands still is exactly what produces an unchanged
            # field once its surroundings have bottomed out - so gating here
            # would blind us precisely when the opponent is stationary, which is
            # when it is easiest to catch. 33 of 126 fixes on the played
            # friendly were lost this way.
            found = max(((r, c) for r in range(self.size) for c in range(self.size)),
                        key=lambda cell: scent[cell[0]][cell[1]])
            if not board.is_open(found):
                return None
            self.previous_fix, self.fix = self.fix, found
            self.fixes += 1
            return found
        if previous is None or not changed(previous, scent, self.size):
            return None
        candidates = None
        if self.fix is not None:
            # It moved at most one step since the last fix, and it cannot be
            # standing in a barrier.
            candidates = [c for c in [self.fix, *board.neighbors4(self.fix)]
                          if board.is_open(c)]
        found = locate_emitter(previous, scent, size=self.size, model=self.model,
                               candidates=candidates)
        if found is None and candidates is not None:
            # Continuity broke - a dropped turn, a model that is not quite the
            # one we negotiated, or a peer that re-serves a stale field. Re-open
            # the scan to the whole board rather than carry a stale fix forward.
            found = locate_emitter(previous, scent, size=self.size, model=self.model)
        if found is None:
            return None
        self.previous_fix, self.fix = self.fix, found
        self.fixes += 1
        return found

    @property
    def velocity(self) -> Cell | None:
        """Displacement between the last two fixes, when it is one orthogonal step."""
        if self.fix is None or self.previous_fix is None:
            return None
        dr = self.fix[0] - self.previous_fix[0]
        dc = self.fix[1] - self.previous_fix[1]
        return (dr, dc) if abs(dr) + abs(dc) == 1 else None

    def possible(self, board: Board) -> list[Cell]:
        """Every cell the opponent could be standing on right now.

        Exactly the fix under a model that serves after emitting; the fix plus
        its open neighbours under one that serves before, since it has had a
        step since the evidence was written.
        """
        if self.fix is None:
            return []
        cells = {self.fix}
        for _ in range(self.lag):
            cells = {n for cell in cells for n in [cell, *board.open_neighbors(cell)]}
        return sorted(c for c in cells if board.is_open(c))

    def projected(self, board: Board, ahead: int = 1) -> Cell | None:
        """Where a straight-running opponent will be ``ahead`` steps from now.

        Velocity comes from two exact fixes rather than from a jittering belief
        peak, so this is a real heading and not a smoothed guess - but it is
        still only a guess about intent, so it is clipped to the last open cell
        along the ray instead of running off the board.
        """
        velocity = self.velocity
        if self.fix is None or velocity is None:
            return None
        cell = self.fix
        for _ in range(self.lag + ahead):
            step = (cell[0] + velocity[0], cell[1] + velocity[1])
            if not board.is_open(step):
                break
            cell = step
        return cell
