"""The two negotiated pheromone physics.

A shared model *name* is not a shared physics: uoh-sqak's registration pins the
evaluation order because the two algebraically-equal spellings are not equal in
IEEE-754 doubles, and a model that rounds nothing propagates that last bit
forever.
"""

from __future__ import annotations

import pytest

from p2p_pursuit.domain.negotiation import scent_model_sha256
from p2p_pursuit.domain.scent import (
    BOOK_V1,
    CENTER_INTENSITY,
    DECAY_RATE,
    REGISTERED_V3,
    ScentField,
    scent_model_document,
)


def test_registered_pins_the_spelling_not_the_algebra() -> None:
    """Their published case: tau=0.05, delta=0.04 -> 0.085, NOT 0.08499999999999999."""
    tau, delta = 0.05, 0.04
    pinned = (1 - DECAY_RATE) * tau + delta
    alternative = tau - DECAY_RATE * tau + delta
    assert pinned == 0.085
    assert alternative == 0.08499999999999999
    assert pinned != alternative, "the two spellings must stay distinguishable"


def test_registered_serves_after_its_own_update() -> None:
    """Freshest cell reads 0.9 on their wire; ours reads 0.81 on the book model."""
    registered = ScentField(7, model=REGISTERED_V3).serve_for_step((3, 3))
    assert registered[3][3] == CENTER_INTENSITY

    book = ScentField(7, model=BOOK_V1)
    book.serve_for_step((3, 3))            # first served field is still empty
    assert book.serve_for_step((3, 3))[3][3] == pytest.approx(0.81)


def test_registered_does_not_round_or_snap_dust() -> None:
    field = ScentField(7, model=REGISTERED_V3)
    field.serve_for_step((0, 0))
    for _ in range(80):
        field.advance((6, 6))              # emit far away; the corner only decays
    corner = field.grid[0][0]
    assert 0.0 < corner < 1e-3, "a dust floor would have snapped this to zero"
    assert round(corner, 4) != corner, "4-dp rounding would have quantised this"


def test_book_model_still_rounds_and_snaps() -> None:
    """The default is unchanged - our published repos play it."""
    field = ScentField(7, model=BOOK_V1)
    field.serve_for_step((0, 0))
    for _ in range(80):
        field.serve_for_step((6, 6))
    assert field.grid[0][0] == 0.0


def test_the_two_models_lock_to_different_hashes() -> None:
    """Rule #23: same name, different physics must REFUSE to start, not drift."""
    assert scent_model_sha256(BOOK_V1) != scent_model_sha256(REGISTERED_V3)
    assert scent_model_document(REGISTERED_V3)["rounding_digits"] is None
    assert scent_model_document(BOOK_V1)["rounding_digits"] == 4


def test_registered_clamps_to_the_focal_cap() -> None:
    field = ScentField(7, model=REGISTERED_V3)
    for _ in range(30):
        field.advance((3, 3))
    assert field.grid[3][3] == CENTER_INTENSITY
