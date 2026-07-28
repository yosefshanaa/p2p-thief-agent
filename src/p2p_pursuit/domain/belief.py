"""Bayesian belief map over the hidden opponent (book ch. 6.4).

Per opponent step: scent likelihood on their *previous* position (the served
field is pre-emission, so its freshest cell marks where they were), then
one-step motion diffusion, then the trust-weighted hint update.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .board import Board, Cell

EPS = 1e-9
SCENT_SHARPNESS = 8.0  # tau**beta strongly favors the freshest trail cells
HINT_STRENGTH = 0.8


@dataclass
class BeliefMap:
    size: int
    grid: list[list[float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.grid:
            u = 1.0 / (self.size * self.size)
            self.grid = [[u] * self.size for _ in range(self.size)]

    @classmethod
    def at(cls, size: int, cell: Cell) -> BeliefMap:
        b = cls(size, [[0.0] * size for _ in range(size)])
        b.grid[cell[0]][cell[1]] = 1.0
        return b

    def _normalize(self, board: Board | None = None) -> None:
        if board is not None:
            for r, c in board.barriers:
                self.grid[r][c] = 0.0
        total = sum(map(sum, self.grid))
        if total <= EPS:  # belief died (contradictory evidence) - reset to uniform
            open_cells = [
                (r, c)
                for r in range(self.size)
                for c in range(self.size)
                if board is None or board.is_open((r, c))
            ]
            u = 1.0 / len(open_cells)
            self.grid = [[0.0] * self.size for _ in range(self.size)]
            for r, c in open_cells:
                self.grid[r][c] = u
            return
        self.grid = [[v / total for v in row] for row in self.grid]

    def scent_update(self, scent: list[list[float]], board: Board) -> None:
        """Multiply by the freshness likelihood of the opponent's served field."""
        peak = max(max(row) for row in scent)
        if peak <= 0.0:
            return
        for r in range(self.size):
            for c in range(self.size):
                w = (scent[r][c] / peak) ** SCENT_SHARPNESS
                self.grid[r][c] *= EPS + w
        self._normalize(board)

    def diffuse(self, board: Board) -> None:
        """One opponent step: probability flows over STAY + open orthogonal moves."""
        nxt = [[0.0] * self.size for _ in range(self.size)]
        for r in range(self.size):
            for c in range(self.size):
                p = self.grid[r][c]
                if p <= 0.0:
                    continue
                targets = [(r, c)] + board.open_neighbors((r, c))
                share = p / len(targets)
                for tr, tc in targets:
                    nxt[tr][tc] += share
        self.grid = nxt
        self._normalize(board)

    def hint_update(self, region: set[Cell] | None, trust: float, board: Board) -> None:
        """Soft evidence: cells outside the hinted region are down-weighted by trust."""
        if not region:
            return
        out_factor = 1.0 - HINT_STRENGTH * trust
        for r in range(self.size):
            for c in range(self.size):
                if (r, c) not in region:
                    self.grid[r][c] *= out_factor
        self._normalize(board)

    def exclude(self, cell: Cell, board: Board) -> None:
        """Hard negative evidence (e.g. a denied capture claim): opponent is NOT here."""
        self.grid[cell[0]][cell[1]] = 0.0
        self._normalize(board)

    def argmax(self) -> Cell:
        return max(
            ((r, c) for r in range(self.size) for c in range(self.size)),
            key=lambda cell: self.grid[cell[0]][cell[1]],
        )

    def mass_in(self, cells: set[Cell]) -> float:
        return sum(self.grid[r][c] for r, c in cells if 0 <= r < self.size and 0 <= c < self.size)

    def entropy(self) -> float:
        return -sum(v * math.log(v) for row in self.grid for v in row if v > EPS)

    def snapshot(self) -> list[list[float]]:
        return [row[:] for row in self.grid]
