"""Stigmergic scent field: 5x5 radial emission, per-full-turn decay (book ch. 4).

The emission kernel is the book's exact figure-4 matrix (center tau = 0.9).
Values are clamped to [0, 0.9] and rounded to 4 decimals after every update
so both peers - and the post-game audit - recompute bit-identical fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Cell

CENTER_INTENSITY = 0.9
DECAY_RATE = 0.10
FIELD_SIZE = 5
ROUND_DIGITS = 4

# Book figure 4: radial falloff around the emitting agent (offsets -2..2).
EMISSION_KERNEL: list[list[float]] = [
    [0.04, 0.14, 0.20, 0.14, 0.04],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.20, 0.62, 0.90, 0.62, 0.20],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.04, 0.14, 0.20, 0.14, 0.04],
]


def scent_model_document() -> dict:
    """The emission+decay model with a numeric example - the pre-series lock payload
    (book rule #23: both teams hash-lock this before the first move)."""
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

    def __post_init__(self) -> None:
        if not self.grid:
            self.grid = [[0.0] * self.size for _ in range(self.size)]

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
