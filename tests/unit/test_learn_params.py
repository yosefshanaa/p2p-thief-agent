"""The doctrine vector: the contract the offline search optimises against."""

from __future__ import annotations

import json

import pytest

from p2p_pursuit.strategy import params
from p2p_pursuit.strategy.params import Doctrine


def test_every_default_sits_inside_its_own_search_box():
    """A default pinned to a bound can only be searched in one direction, which
    silently halves the space and hides a better value on the other side."""
    for key, (low, high, _) in params.SPACE.items():
        value = getattr(Doctrine(), key)
        assert low < value < high, f"{key}={value} sits on the edge of ({low}, {high})"


def test_the_deception_fields_are_out_of_reach_of_the_search():
    """An optimiser tunes only what its objective can punish. Swapping the whole
    deception set between designed and searched values moves the outcome by
    42-46 captures out of 80 - inside the noise - because only `mirror` reads
    hints at all and even it never tries to invert a lie. Left free, the search
    set `lie_candidates` to 1, which picks the single furthest stale cell and
    re-creates the decodable lie v4 removed. These stay at their designed
    values, and a tuned file that names them anyway is ignored, not obeyed.
    """
    for field in params.UNSEARCHABLE:
        assert field not in params.SPACE
        assert hasattr(Doctrine(), field), f"{field} must still exist, just not be searchable"
    smuggled = params.loads(json.dumps({"lie_candidates": 1, "thief_truth_rate": 0.99}))
    assert smuggled.lie_candidates == Doctrine().lie_candidates
    assert smuggled.thief_truth_rate == Doctrine().thief_truth_rate


def test_the_two_role_halves_partition_the_space():
    """A key in neither half would never be searched; a key in both would be
    tuned twice against two different objectives."""
    assert set(params.POLICE_KEYS) | set(params.THIEF_KEYS) == set(params.SPACE)
    assert not set(params.POLICE_KEYS) & set(params.THIEF_KEYS)


def test_vector_round_trip_is_the_identity():
    keys = params.keys_for(None)
    base = Doctrine()
    assert params.from_vector(base, keys, params.to_vector(base, keys)) == base


def test_from_vector_clamps_and_rounds_to_the_space():
    """The sampler is a Gaussian: it will propose out-of-box and fractional
    values, and an integral field like gap_window must never reach a deque."""
    keys = ("gap_window", "w_risk")
    tuned = params.from_vector(Doctrine(), keys, [3.7, 99.0])
    assert tuned.gap_window == 4 and isinstance(tuned.gap_window, int)
    assert tuned.w_risk == params.SPACE["w_risk"][1]


def test_loads_ignores_keys_this_version_dropped():
    """A tuned file outlives the vector that produced it; an unknown key must
    not crash a counted match hours before it is played."""
    tuned = params.loads(json.dumps({"w_risk": 2.0, "w_telepathy": 9.0}))
    assert tuned.w_risk == 2.0
    assert tuned.gap_window == Doctrine().gap_window


def test_the_tuned_file_is_found_from_anywhere(monkeypatch, tmp_path):
    """The doctrine must not depend on the working directory `peer` ran from.
    A missing file does not raise - it quietly plays a weaker policy - so this
    resolves off the package, and the league match would never notice."""
    monkeypatch.chdir(tmp_path)
    assert params.DEFAULT_PATH.is_absolute()
    assert params.DEFAULT_PATH.parent.name == "config"
    assert (params.REPO_ROOT / "src" / "p2p_pursuit").is_dir()


def test_active_reads_the_tuned_file_and_defaults_without_one(tmp_path):
    params.active.cache_clear()
    missing = tmp_path / "absent.json"
    assert params.active(missing) == Doctrine()
    params.active.cache_clear()
    path = tmp_path / "doctrine.json"
    params.save(params.from_vector(Doctrine(), ("gap_window",), [6]), path)
    assert params.active(path).gap_window == 6
    params.active.cache_clear()


@pytest.fixture(autouse=True)
def _clear_cache():
    yield
    params.active.cache_clear()
