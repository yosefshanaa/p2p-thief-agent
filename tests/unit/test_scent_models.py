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
    SUBTRACTIVE_CHEBYSHEV_V1,
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


# -- s82kma9e's kit model ----------------------------------------------------
# Their two published fields ARE the specification. They were sent as the answer
# to our "what is your actual kernel?" question on 2026-08-17, after a friendly
# in which we ran unlocked because we could not reproduce their physics.
THEIR_FIELD_AFTER_EMIT_AT_33 = [
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.0],
    [0.0, 0.2, 0.5, 0.5, 0.5, 0.2, 0.0],
    [0.0, 0.2, 0.5, 0.8, 0.5, 0.2, 0.0],
    [0.0, 0.2, 0.5, 0.5, 0.5, 0.2, 0.0],
    [0.0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
]
THEIR_FIELD_AFTER_MOVE_TO_34 = [
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.1, 0.2, 0.2, 0.2, 0.2, 0.2],
    [0.0, 0.1, 0.4, 0.5, 0.5, 0.5, 0.2],
    [0.0, 0.1, 0.4, 0.7, 0.8, 0.5, 0.2],
    [0.0, 0.1, 0.4, 0.5, 0.5, 0.5, 0.2],
    [0.0, 0.1, 0.2, 0.2, 0.2, 0.2, 0.2],
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
]


def test_subtractive_chebyshev_reproduces_their_two_golden_fields() -> None:
    """Both fields, from one continuous run - the second depends on the first."""
    fld = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1)
    assert fld.serve_for_step((3, 3)) == THEIR_FIELD_AFTER_EMIT_AT_33
    assert fld.serve_for_step((3, 4)) == THEIR_FIELD_AFTER_MOVE_TO_34


def test_their_freshest_cell_is_neither_ours_nor_the_registered_models() -> None:
    """0.81 (book) vs 0.9 (registered) vs 0.8 (theirs): the number that names
    the model. Getting this wrong is a silent disagreement, not an error."""
    peaks = {}
    for model in (BOOK_V1, REGISTERED_V3, SUBTRACTIVE_CHEBYSHEV_V1):
        fld = ScentField(size=7, model=model)
        fld.serve_for_step((3, 3))
        peaks[model] = fld.max_value()
    assert peaks[BOOK_V1] == pytest.approx(0.81)
    assert peaks[REGISTERED_V3] == pytest.approx(0.9)
    assert peaks[SUBTRACTIVE_CHEBYSHEV_V1] == pytest.approx(0.8)


def test_their_rings_are_flat_where_ours_are_graded() -> None:
    """The difference that survives our peak-normalised belief update, and so
    the only one that actually moves where we search."""
    fld = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1)
    served = fld.serve_for_step((3, 3))
    ring1 = [served[3][2], served[3][4], served[2][3], served[4][3],
             served[2][2], served[4][4]]
    assert set(ring1) == {0.5}, "a Chebyshev ring is flat, diagonals included"

    # Ours serves BEFORE its own emission, so the second step is the first one
    # that carries a field at all.
    ours = ScentField(size=7, model=BOOK_V1)
    ours.serve_for_step((3, 3))
    ours_served = ours.serve_for_step((3, 3))
    assert ours_served[3][2] != ours_served[2][2], "ours grades by offset"


def test_their_max_merge_does_not_accumulate_on_a_revisited_cell() -> None:
    """Emission max-merges rather than adds, so standing still cannot pile up
    past the cap - and the current cell stays uniquely maximal, which is what
    keeps our belief argmax on their true position."""
    fld = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1)
    for _ in range(5):
        fld.serve_for_step((3, 3))
    assert fld.grid[3][3] == pytest.approx(0.8)
    assert fld.max_value() == pytest.approx(0.8)


def test_their_model_locks_to_its_own_hash() -> None:
    """Rule #23: the lock must distinguish all three, or it locks nothing."""
    hashes = {scent_model_sha256(m)
              for m in (BOOK_V1, REGISTERED_V3, SUBTRACTIVE_CHEBYSHEV_V1)}
    assert len(hashes) == 3


def test_their_lock_document_is_adopted_byte_for_byte() -> None:
    """s82kma9e's canonical lock, agreed 2026-08-17 for the counted match.

    The physics were already identical; the schema was not, and a lock that
    hashes a different object locks nothing. This pins THEIR hash, so any tidy-up
    of the field names breaks the counted handshake here instead of at kickoff.
    """
    assert scent_model_sha256(SUBTRACTIVE_CHEBYSHEV_V1) == (
        "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4")


def test_the_lock_example_is_what_the_model_actually_does() -> None:
    """The document is only worth hashing if it describes the running code."""
    doc = scent_model_document(SUBTRACTIVE_CHEBYSHEV_V1)
    fld = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1)
    served = fld.serve_for_step(tuple(doc["example"]["emit_center"]))
    for key, value in doc["example"]["after_one_decay"].items():
        r, c = (int(x) for x in key.split(","))
        assert served[r][c] == pytest.approx(value)


# -- najamjad's cut ----------------------------------------------------------
# Same physics, same lock digest, different packet. najamjad cut the transmitted
# grid before the decay and s82kma9e cut it after, and the signed document does
# not say which - so this is a per-opponent term carried in `najamjad.env`, not
# a correction to the default. Both blocks below must stay true at once.


def test_the_default_cut_is_unchanged_for_everyone_else() -> None:
    """s82kma9e's golden fields are a filed counted series - they do not move."""
    fld = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1)
    assert fld.serve_for_step((3, 3)) == THEIR_FIELD_AFTER_EMIT_AT_33
    assert fld.serve_for_step((3, 3))[3][3] == 0.8


def test_serving_before_the_decay_puts_09_on_the_wire() -> None:
    """najamjad read the peak at step 1 and stop the series if it is not 0.9."""
    fld = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1, serve_before_decay=True)
    served = fld.serve_for_step((3, 3))
    assert served[3][3] == 0.9
    assert served[3][2] == 0.6, "ring 1"
    assert served[3][1] == 0.3, "ring 2"


def test_the_stored_grid_is_identical_under_both_cuts() -> None:
    """The whole safety argument: only the snapshot moves, so nothing we
    compute from our own field changes - it is a wire term, not a physics one."""
    late = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1)
    early = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1, serve_before_decay=True)
    for cell in ((3, 3), (3, 4), (2, 4), (2, 4), (1, 4)):
        late.serve_for_step(cell)
        early.serve_for_step(cell)
        assert late.grid == early.grid, f"stored grids diverged at {cell}"


def test_the_early_cut_is_exactly_one_decay_above_the_late_one() -> None:
    late = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1)
    early = ScentField(size=7, model=SUBTRACTIVE_CHEBYSHEV_V1, serve_before_decay=True)
    a, b = late.serve_for_step((3, 3)), early.serve_for_step((3, 3))
    for r in range(7):
        for c in range(7):
            if a[r][c] > 0.0:
                assert round(b[r][c] - a[r][c], 4) == 0.1, f"at {(r, c)}"


def test_the_flag_does_not_touch_the_other_two_models() -> None:
    """It is a subtractive-only term; book and registered must be untouched."""
    for model in (BOOK_V1, REGISTERED_V3):
        off = ScentField(size=7, model=model)
        on = ScentField(size=7, model=model, serve_before_decay=True)
        assert off.serve_for_step((3, 3)) == on.serve_for_step((3, 3))
        assert off.grid == on.grid
