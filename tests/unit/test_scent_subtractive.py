"""`subtractive_chebyshev_v1` against the kit's CORE pheromone vectors.

Scent is transmitted rather than re-derived, so a wrong port here cannot fail
an audit - it just makes our belief map read a physics that is not the one on
the wire, which is worse, because nothing reports it.
"""

from __future__ import annotations

import json
from pathlib import Path

from p2p_pursuit.domain import scent_subtractive as sub
from p2p_pursuit.domain.scent import MODELS, SUBTRACTIVE_V1, ScentField, scent_model_document

VECTORS = Path(__file__).resolve().parents[1] / "vectors" / "kit"
BOARD = 7


def _kit(name: str) -> dict:
    return json.loads((VECTORS / f"{name}.json").read_text(encoding="utf-8"))


def _sparse(grid: list[list[float]]) -> dict[str, float]:
    """Dense grid -> the wire's `{"r,c": v}`, which drops zeros as the kit does."""
    return {f"{r},{c}": v for r, row in enumerate(grid) for c, v in enumerate(row) if v > 0.0}


def _empty(size: int = BOARD) -> list[list[float]]:
    return [[0.0] * size for _ in range(size)]


def test_emission_reproduces_the_kit_field() -> None:
    """The whole 5x5 window: rings of 0.9 / 0.6 / 0.3 around the emitter."""
    vector = _kit("pheromone")["emit"][0]
    grid = _empty()
    sub.emit(grid, tuple(vector["center"]), size=BOARD)
    assert _sparse(grid) == vector["field"]


def test_decay_subtracts_a_constant_rather_than_scaling() -> None:
    """0.9 -> 0.8, not 0.81. This one number is the whole divergence."""
    vector = _kit("pheromone")["decay"][0]
    grid = _empty()
    for key, value in vector["before"].items():
        r, c = (int(p) for p in key.split(","))
        grid[r][c] = value
    sub.decay(grid, size=BOARD, amount=vector["decay"])
    assert _sparse(grid) == vector["after"]


def test_the_outer_ring_dies_in_three_steps() -> None:
    """Why the doctrine cannot simply transfer: this field is a short memory.
    Under the book's multiplicative decay the same cell still reads 0.2187."""
    grid = _empty()
    sub.emit(grid, (3, 3), size=BOARD)
    corner = (1, 1)
    assert grid[corner[0]][corner[1]] == 0.3
    for _ in range(3):
        sub.decay(grid, size=BOARD)
    assert grid[corner[0]][corner[1]] == 0.0
    assert grid[3][3] == 0.6  # the centre survives; only the trail's edge is gone


def test_emission_merges_by_max_so_a_revisit_cannot_exceed_the_emitter() -> None:
    grid = _empty()
    sub.emit(grid, (3, 3), size=BOARD)
    sub.emit(grid, (3, 4), size=BOARD)
    assert max(max(row) for row in grid) == 0.9


def test_a_centre_below_the_minimum_does_not_emit() -> None:
    grid = _empty()
    sub.emit(grid, (3, 3), size=BOARD, intensity=sub.MIN_CENTER_INTENSITY - 0.01)
    assert _sparse(grid) == {}


def test_the_field_serves_after_its_own_update() -> None:
    """Serving order is not pinned by any vector, so it is pinned here and
    declared in the lock document - the two sides must not choose differently.

    It was 0.9 (decay-then-deposit) until s82kma9e's lock settled the question
    the other way: their document says `"order": "deposit_then_decay"` and the
    two golden fields they published require a 0.8 centre. We reproduced both,
    both sides derived the same lock hash, and the counted match was played
    under it (2026-08-17, 6/6 Verified OK). Whoever revisits this: the kit does
    not pin the order, so it is a per-opponent agreement, and this is the one
    we have signed and played.
    """
    field = ScentField(size=BOARD, model=SUBTRACTIVE_V1)
    served = field.serve_for_step((3, 3))
    assert served[3][3] == 0.8


def test_the_model_is_registered_and_locks_to_its_own_hash() -> None:
    from p2p_pursuit.domain.crypto import digest

    assert SUBTRACTIVE_V1 in MODELS
    doc = scent_model_document(SUBTRACTIVE_V1)
    # `name`, not `model`: the document is s82kma9e's schema, adopted verbatim
    # so the two sides hash the same object rather than merely equivalent ones.
    assert doc["name"] == "subtractive_chebyshev_v1"
    others = {digest(scent_model_document(m)) for m in MODELS if m != SUBTRACTIVE_V1}
    assert digest(doc) not in others
