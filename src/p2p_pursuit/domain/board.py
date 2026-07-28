"""Discrete arena: square grid, orthogonal moves, permanent barriers.

Coordinates are ``(row, col)`` with the origin at the top-left corner and
indices starting at 0 (both negotiable via the shared constitution); the
row axis grows downward, so ``N`` decreases the row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Cell = tuple[int, int]

MOVES: dict[str, Cell] = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1), "STAY": (0, 0)}
ORTHOGONAL = ("N", "S", "E", "W")


def target_of(pos: Cell, move: str) -> Cell:
    dr, dc = MOVES[move]
    return (pos[0] + dr, pos[1] + dc)


@dataclass
class Board:
    """Grid state as one peer knows it: size plus all *declared* barriers."""

    size: int
    barriers: set[Cell] = field(default_factory=set)

    def on_board(self, cell: Cell) -> bool:
        r, c = cell
        return 0 <= r < self.size and 0 <= c < self.size

    def is_open(self, cell: Cell) -> bool:
        return self.on_board(cell) and cell not in self.barriers

    def add_barrier(self, cell: Cell) -> None:
        self.barriers.add(cell)

    def neighbors4(self, cell: Cell) -> list[Cell]:
        return [target_of(cell, m) for m in ORTHOGONAL]

    def open_neighbors(self, cell: Cell) -> list[Cell]:
        return [n for n in self.neighbors4(cell) if self.is_open(n)]

    def legal_moves(self, pos: Cell) -> list[str]:
        """STAY plus every orthogonal move whose target is open. Diagonals do not exist."""
        moves = [m for m in ORTHOGONAL if self.is_open(target_of(pos, m))]
        moves.append("STAY")
        return moves

    def is_enclosed(self, pos: Cell) -> bool:
        """All four orthogonal neighbors blocked (barrier or board edge) - a trapped thief."""
        return not self.open_neighbors(pos)

    def clone(self) -> Board:
        return Board(self.size, set(self.barriers))
