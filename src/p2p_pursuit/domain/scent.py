"""Stigmergic scent field: 5x5 radial emission, per-full-turn decay (book ch. 4).

The emission kernel is the book's exact figure-4 matrix (center tau = 0.9).
Values are clamped to [0, 0.9] and rounded to 4 decimals after every update
so both peers - and the post-game audit - recompute bit-identical fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import scent_subtractive
from .board import Cell

CENTER_INTENSITY = 0.9
DECAY_RATE = 0.10
FIELD_SIZE = 5
ROUND_DIGITS = 4
DUST_FLOOR = 0.001

#: Our reading of book ch. 4: the field is served *before* the step's own
#: emission (so the freshest cell an opponent ever sees is 0.81), values are
#: rounded to 4 dp and dust below 1e-3 snaps to zero.
BOOK_V1 = "book_v1"
#: The registered inter-team model (`multiplicative_book_v3`): decay and
#: emission in ONE expression, **no rounding**, no dust floor, and the field
#: served *after* the update - so the freshest cell reads 0.9. Negotiated per
#: opponent, because it is a different physics and not merely a different name.
REGISTERED_V3 = "registered_v3"
#: The kit's *promoted* registered model, adopted for yanell11 (2026-08-23).
#: Algebraically identical to :data:`REGISTERED_V3` - same kernel, same rho,
#: same clamp, same one-expression update, same serve-after-update - and a
#: **different document**, so it locks to a different hash: `934c220d...`
#: against our `0761ca16...`. That is the whole reason it exists as a separate
#: entry. The lock is over the document and never over the behaviour, so two
#: teams running provably identical physics still refuse each other until one
#: of them adopts the other's bytes; yanell11 cannot move because their graded
#: conformance vectors pin theirs, so we hold both documents and declare
#: whichever a given opponent is pinned to.
MULTIPLICATIVE_BOOK_V1 = "multiplicative_book_v1"
#: The reference implementation's physics, CORE in the league's shared kit:
#: flat Chebyshev rings and *subtractive* decay. A different world, not a
#: different spelling - see :mod:`.scent_subtractive`.
SUBTRACTIVE_V1 = "subtractive_chebyshev_v1"
#: Long-form alias. Both names are in use across the test suite and both are
#: the same model string; neither is deprecated.
SUBTRACTIVE_CHEBYSHEV_V1 = SUBTRACTIVE_V1
MODELS = (BOOK_V1, REGISTERED_V3, MULTIPLICATIVE_BOOK_V1, SUBTRACTIVE_V1)
#: Models that share `ScentField.advance` - the registered one-expression
#: update. Membership is what routes a model to that physics, so a document
#: registered without being named here would silently play `book_v1`.
REGISTERED_MODELS = frozenset({REGISTERED_V3, MULTIPLICATIVE_BOOK_V1})

# Book figure 4: radial falloff around the emitting agent (offsets -2..2).
EMISSION_KERNEL: list[list[float]] = [
    [0.04, 0.14, 0.20, 0.14, 0.04],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.20, 0.62, 0.90, 0.62, 0.20],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.04, 0.14, 0.20, 0.14, 0.04],
]


def scent_model_document(model: str = BOOK_V1) -> dict:
    """The emission+decay model with a numeric example - the pre-series lock payload
    (book rule #23: both teams hash-lock this before the first move)."""
    if model == SUBTRACTIVE_V1:
        return scent_subtractive.model_document()
    if model == REGISTERED_V3:
        return {
            "model": "multiplicative_book_v3",
            # The spelling is pinned, not the algebra: the two forms are
            # algebraically equal and NOT equal in IEEE-754 doubles, and a model
            # that rounds nothing propagates that last bit forever.
            "formula": "tau(t+1) = clamp((1 - rho) * tau(t) + delta_tau, 0, 0.9)",
            "evaluation_order": "(1 - rho) * tau + delta",
            "rho": DECAY_RATE,
            "center_intensity": CENTER_INTENSITY,
            "kernel": EMISSION_KERNEL,
            "numeric_example": {"tau": 0.05, "delta": 0.04, "result": 0.085},
            "rounding_digits": None,
            "dust_floor": None,
            "serving": "each step serves the field AFTER that step's own update",
        }
    if model == MULTIPLICATIVE_BOOK_V1:
        # yanell11's bytes, reproduced from their 2026-08-23 message and verified
        # to hash to 934c220d..., which is the value their own vendored vectors
        # pin. Held as a literal rather than derived from the fields above: the
        # physics is shared with `registered_v3`, the *document* is theirs, and
        # deriving it would let one of our constants quietly rewrite their hash.
        return {
            "example": {
                "clamped": 0.9,
                "delta": 0.62,
                "note": "the clamp case: a saturated cell decays, then takes an "
                        "adjacent deposit",
                "raw": 1.4300000000000002,
                "tau": 0.9,
            },
            "family": "scent_model",
            "name": "multiplicative_book_v1",
            "params": {
                "cadence": "per_full_turn",
                "center_intensity": 0.9,
                "clamp": [0.0, 0.9],
                "decay": "multiplicative",
                "decay_rho": 0.1,
                "evaluation_order": "(1 - rho) * tau + delta, then clamp",
                "field_size": 5,
                "initial_field": "empty",
                # Inlined rather than `EMISSION_KERNEL`: their figures are
                # equal to ours today and the document must not depend on that
                # staying true - a change to our constant would otherwise
                # rewrite the hash we agreed with them.
                "kernel": [[0.04, 0.14, 0.20, 0.14, 0.04],
                           [0.14, 0.42, 0.62, 0.42, 0.14],
                           [0.20, 0.62, 0.90, 0.62, 0.20],
                           [0.14, 0.42, 0.62, 0.42, 0.14],
                           [0.04, 0.14, 0.20, 0.14, 0.04]],
                "kernel_source": "book v3.0.0 figure 4 \u2014 printed values, "
                                 "verbatim lookup",
                "order": "decay_then_deposit",
                "receiver_side_decay": False,
                "rounding_decimals": None,
                "transmitted": False,
                "update": "tau' = clamp((1 - rho) * tau + kernel_delta, 0, "
                          "center_intensity)",
            },
        }
    return {
        "formula": "tau(t+1) = min(0.9, max(0, (1 - rho) * tau(t) + delta_tau))",
        "rho": DECAY_RATE,
        "center_intensity": CENTER_INTENSITY,
        "kernel": EMISSION_KERNEL,
        "numeric_example": {"tau_0": 0.9, "after_one_decay": 0.81},
        "rounding_digits": ROUND_DIGITS,
        "serving": "each step serves the field BEFORE that step's emission",
    }


@dataclass
class ScentField:
    """One agent's own pheromone field; the opponent reads it, never the owner."""

    size: int
    grid: list[list[float]] = field(default_factory=list)
    model: str = BOOK_V1
    #: Subtractive only: snapshot *between* the emission and the decay, so the
    #: freshest served centre reads 0.9 rather than 0.8. The kit's document
    #: pins `order: deposit_then_decay` for the grid but never says which side
    #: of the decay the *packet* is cut from, so the two readings are both
    #: defensible and neither is inferable from the digest - see
    #: `PeerConfig.scent_serve_before_decay`. Per opponent, never global.
    serve_before_decay: bool = False

    def __post_init__(self) -> None:
        if not self.grid:
            self.grid = [[0.0] * self.size for _ in range(self.size)]

    def advance(self, center: Cell) -> None:
        """Registered model: decay and emission in one pinned expression.

        No rounding and no dust floor - the registration's own words are "with
        NO rounding", and a floor would be another silent divergence.
        """
        half = FIELD_SIZE // 2
        for r in range(self.size):
            for c in range(self.size):
                dr, dc = r - center[0], c - center[1]
                delta = (EMISSION_KERNEL[dr + half][dc + half]
                         if abs(dr) <= half and abs(dc) <= half else 0.0)
                value = (1.0 - DECAY_RATE) * self.grid[r][c] + delta
                self.grid[r][c] = min(CENTER_INTENSITY, max(0.0, value))

    def serve_for_step(self, center: Cell) -> list[list[float]]:
        """Apply one own-step and return the field that step must serve.

        The *ordering* is the whole difference between the two models, and it
        has to be stated once: the live engine and the audit replay both call
        this, so a field we serve and a field the auditor recomputes cannot
        drift apart without the drift being in this one method.
        """
        if self.model == SUBTRACTIVE_V1:
            # deposit_then_decay, NOT decay-then-deposit. The kit pins no vector
            # for this and the two orders differ by a whole step: emit-first
            # serves a 0.8 centre, decay-first serves 0.9. s82kma9e's signed lock
            # says `"order": "deposit_then_decay"` and their two published golden
            # fields require 0.8, so this is the order we contracted, locked and
            # played the counted match under (2026-08-17, 6/6 Verified OK).
            #
            # najamjad read the same document the other way and cut the packet
            # before the decay. Both orders leave the *stored* grid identical -
            # only the snapshot moves - so this changes what we transmit and
            # nothing we compute. It is per-opponent because the two teams
            # genuinely disagree and the digest cannot settle it.
            scent_subtractive.emit(self.grid, center, size=self.size)
            if self.serve_before_decay:
                served = self.snapshot()
                scent_subtractive.decay(self.grid, size=self.size)
                return served
            scent_subtractive.decay(self.grid, size=self.size)
            return self.snapshot()
        if self.model in REGISTERED_MODELS:
            self.advance(center)
            return self.snapshot()
        served = self.snapshot()
        self.emit(center)
        self.decay()
        return served

    def emit(self, center: Cell) -> None:
        """Deposit the radial kernel around ``center``, clamped to the focal cap."""
        half = FIELD_SIZE // 2
        for dr in range(-half, half + 1):
            for dc in range(-half, half + 1):
                r, c = center[0] + dr, center[1] + dc
                if 0 <= r < self.size and 0 <= c < self.size:
                    add = EMISSION_KERNEL[dr + half][dc + half]
                    self.grid[r][c] = round(
                        min(CENTER_INTENSITY, self.grid[r][c] + add), ROUND_DIGITS
                    )

    def decay(self) -> None:
        """One full-turn decay tick: tau *= (1 - rho); dust below 1e-3 snaps to zero
        (a higher cutoff than the rounding step, so no value can get stuck)."""
        for r in range(self.size):
            for c in range(self.size):
                v = round(self.grid[r][c] * (1.0 - DECAY_RATE), ROUND_DIGITS)
                self.grid[r][c] = v if v >= 0.001 else 0.0

    def snapshot(self) -> list[list[float]]:
        return [row[:] for row in self.grid]

    def max_value(self) -> float:
        return max(max(row) for row in self.grid)
