"""Invert the scent channel: recover the emitter's cell from two served fields.

Both brains used to estimate the opponent's position as ``argmax`` of the served
scent field. Replayed against the ground truth in our own sealed logs, that
estimator names the emitter's cell **219 times in 1,935** - 11% - because the
field *saturates*: emission adds the book's kernel and clamps at 0.9, so after a
handful of steps a whole swathe of cells sits at the cap and 91% of served
fields have between 6 and 20 cells tied at the maximum. ``max()`` then returns
whichever tied cell row-major iteration reaches first, which is a scan artefact
biased toward the top-left corner - not a position.

The field is not weakly informative, though; it is *fully* informative, and the
old estimator was simply throwing the information away. One step of the model is
a known function of one unknown - the emitter's cell - so the honest reading is
to invert it: replay the negotiated model forward from the previously served
field for each of the 49 candidate centres and keep the one that reproduces the
field we actually received. Over the same 1,935 transitions, spanning 81
sub-games and all three registered models, that is exact **1,935 times out of
1,935**. ``p2p-pursuit learn review`` re-runs both numbers.

Replaying :class:`~.scent.ScentField` itself, rather than re-deriving any
algebra here, is what makes this model-agnostic: whichever physics a match
negotiated is the physics that gets inverted, including its serve order, its
rounding and its clamping. What differs between models is only the *lag*, which
:func:`fix_lag` names:

* ``book_v1`` serves the field BEFORE the step's own emission, so a fix from the
  two latest fields names where the emitter stood one step ago.
* ``registered_v3`` and ``subtractive_chebyshev_v1`` serve AFTER the update, so
  the same fix names where it stands now.

Ambiguity is reported rather than guessed at. A subtractive field merges by max,
so an emitter re-lighting ground that is already brighter changes nothing, and
several centres can explain one transition equally well; when the argmin is not
unique this returns ``None`` and the caller keeps whatever it already believed.
"""

from __future__ import annotations

from . import scent_subtractive
from .board import Cell
from .scent import BOOK_V1, REGISTERED_MODELS, SUBTRACTIVE_V1, ScentField

Field = list[list[float]]

#: Models whose served field already contains that step's own emission. For
#: these a fix from the two latest fields names where the emitter stands *now*;
#: for ``book_v1``, which serves before emitting, it names where it stood one
#: step ago. Getting this backwards costs a whole step of lead and is silent -
#: validated against the archive, the fix is exact under both conventions and
#: simply answers a different question.
SERVES_AFTER_EMISSION = REGISTERED_MODELS | {SUBTRACTIVE_V1}


def fix_lag(model: str) -> int:
    """Steps between a fix from the two latest fields and the emitter's cell now."""
    return 0 if model in SERVES_AFTER_EMISSION else 1

#: Two fields this close are the same field. A repeated serve carries no new
#: evidence (it happens when a turn arrives without an intervening opponent
#: step), and "fit the centre that best explains no change" is nonsense.
UNCHANGED = 1e-12

#: How much of the observed change a candidate may leave unexplained and still
#: be believed, as a fraction of the change itself. A correct model at the
#: correct centre reproduces the field to the last decimal, so the residual is
#: ~0 and any positive tolerance accepts it; a foreign peer whose physics is not
#: quite the one we negotiated leaves a residual on the scale of the change
#: itself, and there the honest answer is "no fix" rather than a best-of-a-bad-
#: set cell that the brains would then act on as though it were exact.
TOLERANCE = 0.25


def _residual(a: Field, b: Field, size: int, cutoff: float) -> float:
    """Sum of squared differences, abandoned once it cannot win."""
    total = 0.0
    for r in range(size):
        row_a, row_b = a[r], b[r]
        for c in range(size):
            diff = row_a[c] - row_b[c]
            total += diff * diff
        if total > cutoff:
            return total
    return total


def changed(previous: Field, current: Field, size: int) -> bool:
    """Did the served field move at all since the last one we saw?"""
    return any(abs(previous[r][c] - current[r][c]) > UNCHANGED
               for r in range(size) for c in range(size))


def locate_emitter(previous: Field, current: Field, *, size: int,
                   model: str = BOOK_V1,
                   serve_before_decay: bool = False,
                   candidates: list[Cell] | None = None,
                   tolerance: float = TOLERANCE) -> Cell | None:
    """The cell whose emission turns ``previous`` into ``current``, if unique.

    ``candidates`` narrows the scan to the cells the emitter could physically
    have reached - the caller's previous fix and its neighbours. That is both
    the cheap path (5 replays instead of 49) and a continuity check: a fix that
    cannot be reached from the last one is not a fix, it is noise.

    Returns ``None`` rather than a guess in three cases: the field did not
    change, two candidates explain it equally well, or the best of them does not
    explain it well enough (see :data:`TOLERANCE`). The last is what keeps this
    safe against a peer whose implementation of the negotiated model differs
    from ours - a live risk, since we have played three different models and
    each was somebody else's document.
    """
    if not changed(previous, current, size):
        return None
    cells = candidates if candidates is not None else [
        (r, c) for r in range(size) for c in range(size)]
    best: Cell | None = None
    best_cost = float("inf")
    ties = 0
    for cell in cells:
        grid = [row[:] for row in previous]
        if serve_before_decay:
            # `previous` is their *packet*, cut before their decay, so it is not
            # their stored grid - it is one decay higher than it. Apply the decay
            # they applied after cutting it and we are standing on their state
            # again. Skip this and every candidate is scored against a grid that
            # is uniformly 0.1 too high, which does not merely add noise: it
            # rescales the residual and silently moves the argmin.
            scent_subtractive.decay(grid, size=size)
        trial = ScentField(size, grid, model, serve_before_decay=serve_before_decay)
        served = trial.serve_for_step(cell)
        # Compare like with like: what they would have *transmitted*. For the
        # other orders that is the post-step grid, which is what `trial.grid`
        # holds; when the packet is cut early the two are a decay apart.
        cost = _residual(served if serve_before_decay else trial.grid,
                         current, size, best_cost)
        if cost < best_cost:
            best, best_cost, ties = cell, cost, 1
        elif cost == best_cost:
            ties += 1
    if best is None or ties != 1:
        return None
    scale = _residual(previous, current, size, float("inf"))
    return best if best_cost <= tolerance * scale else None
