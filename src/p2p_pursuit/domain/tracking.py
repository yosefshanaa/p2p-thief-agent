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
from .scent import BOOK_V1
from .scent_locate import changed, fix_lag, locate_emitter

Field = list[list[float]]


def unique_peak(scent: Field, size: int) -> Cell | None:
    """The emitter's own cell, when the served field names it outright.

    A served field is one of two shapes, and which one it is decides whether
    inverting it is worth anything:

    * **Saturated.** ``book_v1`` and ``registered_v3`` add emission and clamp at
      a cap, so after a few steps a whole region sits *at* the cap - measured on
      our own implementation, 6 cells tied at the maximum by step 4 and 15 by
      step 12. ``max`` then returns whichever tied cell row-major order reaches
      first, which is a bias toward the top-left corner, and the estimator this
      replaced was right 1 time in 9. These fields must be inverted.
    * **Peaked.** ``subtractive_chebyshev_v1`` merges by max and decays by
      subtraction, so the freshest cell stands alone - 1 cell at the maximum on
      every step of the same trace. So does a *memoryless snapshot*: a peer that
      transmits only the current kernel rather than an accumulated field. In both
      cases the peak IS the emitter and inverting is strictly worse, because a
      stationary emitter produces a transition no centre uniquely explains and
      the inverse correctly reports "no fix".

    Keying this on the *field* rather than on the negotiated model matters, and
    it is the difference between winning and losing a match. uoh-ay26 negotiated
    `subtractive_chebyshev_v1` and served a bare 5x5 kernel in absolute board
    coordinates - 25 cells inland, 16 clipped - with no history at all. Replayed
    against that wire format our inverse fits 2 turns in 10; we played all six
    sub-games of that friendly effectively blind and lost 6-0. Nothing stops the
    next opponent doing the same under `book_v1`, which is our own default, and
    a model-keyed test would blind us again on a format we have already seen.
    """
    best = max(((r, c) for r in range(size) for c in range(size)),
               key=lambda cell: scent[cell[0]][cell[1]])
    top = scent[best[0]][best[1]]
    if top <= 0.0:
        return None
    tied = sum(1 for r in range(size) for c in range(size)
               if scent[r][c] >= top - 1e-9)
    return best if tied == 1 else None


class OpponentTracker:
    """Where the opponent is, read off the field it is required to publish."""

    def __init__(self, size: int, model: str = BOOK_V1,
                 serve_before_decay: bool = False) -> None:
        self.size = size
        self.model = model
        # Their serve order, not ours - though under a negotiated contract the
        # two are the same value. `unique_peak` does not care (the emitter's
        # cell is the unique maximum at 0.8 or at 0.9); the replay inverse does.
        self.serve_before_decay = serve_before_decay
        # Unchanged by the packet's cut point: an early-cut packet still carries
        # this step's own emission, so it is still lag 0.
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
        found = unique_peak(scent, self.size)
        if found is not None:
            # Deliberately BEFORE the changed() gate. That gate exists because a
            # transition is the evidence the inverse consumes, so an unchanged
            # field carries none. A peak consumes the field itself, and an
            # emitter that stands still is exactly what produces an unchanged
            # field once its surroundings have bottomed out - so gating here
            # would blind us precisely when the opponent is stationary, which is
            # when it is easiest to catch. 33 of 126 fixes on the played
            # friendly were lost that way.
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
                               serve_before_decay=self.serve_before_decay,
                               candidates=candidates)
        if found is None and candidates is not None:
            # Continuity broke - a dropped turn, a model that is not quite the
            # one we negotiated, or a peer that re-serves a stale field. Re-open
            # the scan to the whole board rather than carry a stale fix forward.
            found = locate_emitter(previous, scent, size=self.size, model=self.model,
                                   serve_before_decay=self.serve_before_decay)
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
