"""A search box that can hold a dead threshold is a bug in the search box.

v7 set `police_fresh_min` to 0.849118 and `thief_fresh_min` to 0.850407. The
highest value `book_v1` can ever serve is **0.81** - it serves the field before
the step's own emission, and emission clamps at 0.9 which then decays by a
tenth. So both trail branches were switched off for every match played under
that physics, and nothing said so: an objective cannot punish a feature that
never fires, and the search duly wandered into a region where it never did.
Instrumented in the lab afterwards, the police's trail test fired 0 times in
2,629 turns.

The fix is not a better search. It is a box the search cannot leave.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2p_pursuit.domain.scent import MODELS, ScentField
from p2p_pursuit.strategy import params

REPO = Path(__file__).resolve().parents[2]
WALK = [(3, 3), (3, 4), (4, 4), (4, 5), (5, 5), (5, 4), (4, 4), (3, 4)]
THRESHOLDS = ("police_fresh_min", "thief_fresh_min")


def ceiling(model: str) -> float:
    """The highest intensity this model can actually put on the wire."""
    field = ScentField(7, model=model)
    return max(max(max(row) for row in field.serve_for_step(cell)) for cell in WALK)


def test_the_lowest_ceiling_is_what_the_box_must_respect():
    lowest = min(ceiling(model) for model in MODELS)
    assert lowest == pytest.approx(0.80), (
        f"the models' served ceilings are "
        f"{ {m: ceiling(m) for m in MODELS} } - if the lowest moved, so must the bounds")


@pytest.mark.parametrize("key", THRESHOLDS)
def test_no_freshness_threshold_can_be_searched_above_what_is_servable(key):
    low, high, _ = params.SPACE[key]
    assert high <= min(ceiling(model) for model in MODELS), (
        f"{key} may be searched up to {high}, which no served field reaches - "
        f"that is exactly how v7's trail branch went silently dead")
    assert low < high


@pytest.mark.parametrize("key", THRESHOLDS)
def test_every_committed_doctrine_is_repaired_on_load(key):
    """Old files carry the dead values; clamping happens where they are parsed."""
    for path in sorted(REPO.glob("config/doctrine*.json")):
        loaded = getattr(params.active(path), key)
        assert loaded <= params.SPACE[key][1], f"{path.name} loaded {key}={loaded}"


def test_every_default_sits_strictly_inside_its_own_box():
    """So the search can move either way from the shipped value, on every axis."""
    shipped = params.Doctrine()
    for key, (low, high, _) in params.SPACE.items():
        value = getattr(shipped, key)
        assert low <= value <= high, f"{key}={value} is outside [{low}, {high}]"


def test_the_role_split_covers_the_space_exactly_once():
    """The prefix rule that used to derive this filed every new key under the
    thief, so a `--role police` search silently left three police keys alone."""
    assert set(params.POLICE_KEYS) | set(params.THIEF_KEYS) == set(params.SPACE)
    assert not set(params.POLICE_KEYS) & set(params.THIEF_KEYS)


@pytest.mark.parametrize("key", ["pounce_floor", "flee_bias", "w_cut", "chase_bias", "w_strike"])
def test_the_v8_keys_are_searchable_and_filed_under_the_role_that_reads_them(key):
    assert key in params.SPACE
    police = key in ("pounce_floor", "flee_bias", "w_cut")
    assert (key in params.POLICE_KEYS) is police
    assert (key in params.THIEF_KEYS) is not police


def test_a_doctrine_file_may_not_name_a_key_the_dataclass_does_not_have():
    """A typo in a committed vector is silently ignored at load, forever."""
    known = set(vars(params.Doctrine()))
    for path in sorted(REPO.glob("config/doctrine*.json")):
        unknown = set(json.loads(path.read_text(encoding="utf-8"))) - known
        assert not unknown, f"{path.name} carries unknown keys {sorted(unknown)}"
