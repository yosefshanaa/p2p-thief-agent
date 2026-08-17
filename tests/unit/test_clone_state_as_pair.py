"""A `state` that is a bare `[row, col]` pair, which is gal-roy1's record shape.

The failure this guards against is silent and looks like something else
entirely: every opponent record is dropped for having no position, the cloner
reports "0 decisions", and that is indistinguishable from an opponent who never
sent an audit package. Measured 2026-08-17 on 130 sealed records.
"""

from __future__ import annotations

from p2p_pursuit.learn.clone_data import samples_from_log

# Their real shape, copied from
# results/police-ahk-yosi-vs-gal-roy1-20260817T150610/log_..._g01.json
THEIRS = [
    {"step": 1, "role": "THIEF", "state": [3, 4], "move": "MOVE:E", "intent": "truth",
     "hint": "moving east, the alleys here are calm enough in New York"},
    {"step": 2, "role": "THIEF", "state": [4, 4], "move": "MOVE:S", "intent": "lie",
     "hint": "resting north by the station"},
    {"step": 3, "role": "THIEF", "state": [4, 5], "move": "MOVE:E", "intent": "truth",
     "hint": "slipping east past the old market"},
]
MINE = [
    {"kind": "step", "role": "police", "step": 1, "pos_before": [0, 0], "pos_after": [1, 0],
     "move": "S", "barrier": None},
    {"kind": "step", "role": "police", "step": 2, "pos_before": [1, 0], "pos_after": [1, 1],
     "move": "E", "barrier": None},
    {"kind": "step", "role": "police", "step": 3, "pos_before": [1, 1], "pos_after": [1, 2],
     "move": "E", "barrier": None},
]


def _log(theirs: list[dict]) -> dict:
    return {"perspective": "police", "my_records": MINE, "opponent_records": theirs}


def test_a_state_pair_yields_decisions() -> None:
    samples = samples_from_log(_log(THEIRS))
    assert samples, "a bare [row, col] state must not read as 'no position'"
    assert all(s.role == "thief" for s in samples)


def test_the_decision_is_read_from_where_they_stood_not_where_they_landed() -> None:
    """Their step-2 decision was taken from the cell step 1 left them on."""
    sample = samples_from_log(_log(THEIRS))[0]
    assert sample.pos == (3, 4)
    assert sample.move == "S"
    assert sample.pursuer == (1, 0)  # where we stood when they chose


def test_the_reference_state_string_still_works() -> None:
    """The spelling this function already handled must not regress."""
    theirs = [dict(r, state=f"grid=7;self=[{r['state'][0]}, {r['state'][1]}]") for r in THEIRS]
    assert samples_from_log(_log(theirs))


def test_a_state_that_is_not_a_position_is_not_mistaken_for_one() -> None:
    """Two-element lists that are not coordinates must not be read as cells."""
    theirs = [dict(r, state=["north", "east"]) for r in THEIRS]
    assert samples_from_log(_log(theirs)) == []
