"""`subtractive_chebyshev_v1` - the reference implementation's scent physics.

A third registered model beside the book's two multiplicative readings. It is
here because the league's shared conformance kit
(`copthief-league-protocol`, SPEC section 5) carries it as CORE and several
teams build against it, so a peer that can only speak the book's physics has to
argue its way into every match.

It is genuinely a different world, not a different spelling:

    book (ours)      centre 0.9, kernel 0.62 / 0.42 / 0.20 / 0.14 / 0.04,
                     decay tau *= 0.9   -> a trail fades but effectively never dies
    this model       flat Chebyshev rings 0.9 / 0.6 / 0.3,
                     decay v -= 0.1     -> the outer ring is gone in three steps

That decay is the part strategy feels. A subtractive field is a *short* memory,
so trail-age reasoning calibrated on multiplicative traces reads it wrong - see
`docs/STRATEGY.md`. Adopting the physics without re-searching the doctrine under
it is measured, not theoretical: it cost roughly two thirds of our captures
against uoh-sqak.

Nothing here can void a game. Scent maps are transmitted and absorbed, never
re-derived cross-team, so a mismatch costs accuracy rather than an audit.
"""

from __future__ import annotations

from .board import Cell

#: Chebyshev falloff is derived, not tabulated: `intensity / (half + 1)`, which
#: on the default 5-wide window and centre 0.9 gives the kit's 0.9/0.6/0.3.
FIELD_SIZE = 5
CENTER_INTENSITY = 0.9
DECAY_PER_STEP = 0.10
ROUND_DIGITS = 3
#: A centre below this does not emit at all (kit SPEC section 5). At a constant
#: 0.9 centre the gate never fires, but a caller that lowers the centre by
#: agreement gets the registered behaviour rather than ours.
MIN_CENTER_INTENSITY = 0.5


def model_document() -> dict:
    """The pre-series lock payload (book rule #23, kit `locked_model`).

    Both peers hash this and compare hashes before the first move, so every
    field that changes a number has to be *in* here - including the serving
    order, which no vector pins and which silently shifts every reading by one
    step if the two sides choose differently.
    """
    return {
        "model": "subtractive_chebyshev_v1",
        "source": "copthief-league-protocol SPEC section 5 (CORE)",
        "emission": ("value = round(max(0, intensity - falloff * chebyshev), 3), "
                     "falloff = intensity / (half + 1), half = grid_size // 2"),
        "composition": "merged into the trail by max, never summed",
        "decay": "round(max(0, v - decay), 3) once per game step",
        "decay_per_step": DECAY_PER_STEP,
        "center_intensity": CENTER_INTENSITY,
        "min_center_intensity": MIN_CENTER_INTENSITY,
        "field_size": FIELD_SIZE,
        "rounding_digits": ROUND_DIGITS,
        "numeric_example": {"rings": [0.9, 0.6, 0.3], "after_one_decay": [0.8, 0.5, 0.2]},
        "serving": "each step serves the field AFTER that step's own update",
        "transmitted": "only cells with value > 0",
    }


def emit(grid: list[list[float]], center: Cell, *, size: int,
         intensity: float = CENTER_INTENSITY) -> None:
    """Merge one radial emission into ``grid`` in place, by max.

    By max rather than by sum: two visits to the same cell leave one trail at
    full strength, not a cell brighter than the emitter itself.
    """
    if intensity < MIN_CENTER_INTENSITY:
        return
    half = FIELD_SIZE // 2
    falloff = intensity / (half + 1)
    for dr in range(-half, half + 1):
        for dc in range(-half, half + 1):
            r, c = center[0] + dr, center[1] + dc
            if not (0 <= r < size and 0 <= c < size):
                continue
            value = round(max(0.0, intensity - falloff * max(abs(dr), abs(dc))), ROUND_DIGITS)
            grid[r][c] = max(grid[r][c], value)


def decay(grid: list[list[float]], *, size: int,
          amount: float = DECAY_PER_STEP) -> None:
    """Subtract a constant from every cell, clamped at zero, in place."""
    for r in range(size):
        for c in range(size):
            grid[r][c] = round(max(0.0, grid[r][c] - amount), ROUND_DIGITS)
