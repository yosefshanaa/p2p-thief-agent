"""The scent field on the wire: 7x7 matrix <-> their {"r,c": value} grid.

Split out of :mod:`.interop_codec` (§3.2) because both the terms half and the
turn-message half need it and neither owns it.
"""

from __future__ import annotations

from typing import Any

Matrix = list[list[float]]


def scent_to_grid(matrix: Matrix) -> dict[str, float]:
    """Our dense matrix -> their sparse ``{"r,c": intensity}`` (zeros dropped)."""
    return {f"{r},{c}": value
            for r, row in enumerate(matrix)
            for c, value in enumerate(row) if value > 0.0}


def grid_to_scent(grid: dict[str, Any], size: int) -> Matrix:
    """Their sparse grid -> our dense ``size``x``size`` matrix (unknown cells 0.0)."""
    matrix: Matrix = [[0.0] * size for _ in range(size)]
    for key, value in grid.items():
        r, c = (int(part) for part in str(key).split(","))
        if 0 <= r < size and 0 <= c < size:
            matrix[r][c] = float(value)
    return matrix
