"""The scent channel is invertible, and that is the whole point of it.

Both brains used to read the opponent's position off ``argmax`` of its served
field. The archive says that names the emitter 11% of the time, because the field
saturates and 91% of served fields have 6-20 cells tied at the maximum. One step
of the model is a known function of one unknown, so the honest reading is to
solve for it - these tests pin that the solve is exact under every negotiated
model, and that it says "I don't know" rather than guessing when it cannot be.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.scent import BOOK_V1, REGISTERED_V3, SUBTRACTIVE_V1, ScentField
from p2p_pursuit.domain.scent_locate import SERVES_AFTER_EMISSION, fix_lag, locate_emitter

SIZE = 7
MODELS = (BOOK_V1, REGISTERED_V3, SUBTRACTIVE_V1)
WALK = [(3, 3), (3, 4), (4, 4), (4, 5), (5, 5), (5, 4), (5, 3), (4, 3), (3, 3), (3, 2)]


def serve(model: str, walk: list[tuple[int, int]]) -> list[list[list[float]]]:
    """Every field an agent walking ``walk`` would publish, in order."""
    field = ScentField(SIZE, model=model)
    return [field.serve_for_step(cell) for cell in walk]


@pytest.mark.parametrize("model", MODELS)
def test_the_inverse_recovers_every_step_of_a_walk(model):
    """Consecutive served fields name the emitter exactly, under each physics."""
    fields = serve(model, WALK)
    lag = fix_lag(model)
    for i in range(1, len(fields)):
        found = locate_emitter(fields[i - 1], fields[i], size=SIZE, model=model)
        # A model that serves after emitting reports the step that produced the
        # newer field; one that serves before reports the step before it.
        assert found == WALK[i - lag], f"{model} step {i}: got {found}"


def argmax_hits(model: str) -> int:
    """How often the old estimator - argmax of the served field - was right."""
    fields = serve(model, WALK)
    hits = 0
    for i in range(1, len(fields)):
        scent = fields[i]
        argmax = max(((r, c) for r in range(SIZE) for c in range(SIZE)),
                     key=lambda cell: scent[cell[0]][cell[1]])
        hits += argmax == WALK[i - fix_lag(model)]
    return hits


@pytest.mark.parametrize("model", (BOOK_V1, REGISTERED_V3))
def test_the_argmax_it_replaces_fails_under_the_additive_models(model):
    """Emission *adds* and clamps, so a whole region pins at the cap and ties."""
    assert argmax_hits(model) < len(WALK) - 1, (
        f"if {model}'s argmax were exact this module would be pointless - the "
        f"whole finding is that it is not")


def test_the_argmax_is_exact_under_subtractive_which_is_the_leak_not_a_fix():
    """Worth pinning as the *opposite* result, because it cuts both ways.

    `subtractive_chebyshev_v1` merges by max and decays by subtraction, so the
    freshest cell stands alone and the argmax names it every time. That is why
    this module changes nothing for a match negotiated under that model - and
    why our thief's own cell was readable straight off the field it published in
    one, which is how gal-roy1 dropped a barrier on it.
    """
    assert argmax_hits(SUBTRACTIVE_V1) == len(WALK) - 1


def test_an_unchanged_field_is_not_evidence():
    """A repeated serve carries no new information and must not be fitted."""
    fields = serve(BOOK_V1, WALK)
    assert locate_emitter(fields[3], fields[3], size=SIZE, model=BOOK_V1) is None


def test_a_tie_is_reported_as_no_fix_rather_than_guessed():
    """Two centres that explain the transition equally well name neither."""
    flat = [[0.0] * SIZE for _ in range(SIZE)]
    # A field that cannot change: subtractive emission merges by max, so
    # emitting into ground already at the ceiling leaves it identical - and any
    # centre far from the lit region explains that equally well.
    assert locate_emitter(flat, flat, size=SIZE, model=SUBTRACTIVE_V1) is None


def test_candidates_restrict_the_scan_to_reachable_cells():
    """The continuity path: only cells the emitter could have reached compete."""
    fields = serve(BOOK_V1, WALK)
    board = Board(SIZE)
    truth = WALK[2]
    near = locate_emitter(fields[2], fields[3], size=SIZE, model=BOOK_V1,
                          candidates=[truth, *board.neighbors4(truth)])
    assert near == truth
    # Offered only cells it cannot have emitted from, none of them explains the
    # change, so the answer is "no fix" - not the least-bad of a bad set. A
    # brain acts on a fix as though it were exact, so a guess here is worse
    # than silence.
    assert locate_emitter(fields[2], fields[3], size=SIZE, model=BOOK_V1,
                          candidates=[(0, 0), (6, 6)]) is None


def test_a_model_that_is_not_the_one_they_served_is_refused():
    """The foreign-peer guard: three models are in play and each is negotiated.

    Inverting a `subtractive_chebyshev_v1` transition with the book's physics
    leaves a residual on the scale of the change itself, and that has to read as
    "I cannot tell", because a wrong fix is acted on exactly as confidently as a
    right one.
    """
    fields = serve(SUBTRACTIVE_V1, WALK)
    wrong = [locate_emitter(a, b, size=SIZE, model=BOOK_V1)
             for a, b in zip(fields, fields[1:], strict=False)]
    assert wrong.count(None) > len(wrong) // 2, (
        f"the wrong physics produced {len(wrong) - wrong.count(None)} confident "
        f"fixes out of {len(wrong)}")


def test_lag_matches_the_serve_order_each_model_documents():
    assert fix_lag(BOOK_V1) == 1, "book_v1 serves before its own emission"
    for model in SERVES_AFTER_EMISSION:
        assert fix_lag(model) == 0


def test_it_recovers_our_own_cells_from_a_sealed_league_log():
    """Against real bytes, not a simulation: the counted match vs gal-roy1.

    Read-only, and deliberately a *played* log - the archive is the only place
    the saturation this module answers actually shows up at full strength.
    """
    log = json.loads(Path(
        "matches/gal-roy1-counted/police-ahk-yosi-vs-gal-roy1-20260817T173302/"
        "log_ahk-yosi-vs-gal-roy1_g01.json").read_text(encoding="utf-8"))
    steps = sorted((r for r in log["my_records"] if r.get("kind") == "step"),
                   key=lambda r: r["step"])
    pairs = list(zip(steps, steps[1:], strict=False))
    found = [locate_emitter(a["scent"], b["scent"], size=SIZE, model=BOOK_V1)
             == tuple(a["pos_after"]) for a, b in pairs]
    assert all(found), f"{found.count(False)} of {len(found)} transitions missed"
