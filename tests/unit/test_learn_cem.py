"""The optimiser's three honesty properties, each tested on its own.

CEM on a noisy objective fails quietly - it reports a number that does not
survive fresh seeds - so the properties that make it trustworthy are asserted
rather than assumed.
"""

from __future__ import annotations

from p2p_pursuit.learn import cem
from p2p_pursuit.strategy.params import Doctrine, keys_for


def test_it_climbs_a_known_hill():
    """A sanity floor: on a smooth objective with a unique optimum the search
    must actually find it, or nothing downstream means anything."""
    peak = [0.8, 0.2, 0.5]

    def batch(points):
        return [-sum((v - t) ** 2 for v, t in zip(p, peak, strict=True)) for p in points]

    result = cem.search_unit(3, batch, generations=25, population=30, seed=1)
    assert all(abs(v - t) < 0.05 for v, t in zip(result.best, peak, strict=True))
    assert result.best_score > result.baseline


def test_the_incumbent_is_always_candidate_zero():
    """Elitism: the running mean is re-scored every generation on that
    generation's seeds, so a lucky elite set cannot walk the mean downhill."""
    seen: list[list[float]] = []

    def batch(points):
        seen.append(points[0])
        return [0.0] * len(points)

    start = [0.25] * 4
    cem.search_unit(4, batch, start=start, generations=3, population=6, seed=2)
    assert seen[0] == start, "generation 1 must score the starting point itself"
    assert len(seen) == 3


def test_the_distribution_never_collapses():
    """Without a variance floor the search converges onto the first plausible
    basin and then stops exploring - it looks converged and is merely stuck."""
    widths = []

    def batch(points):
        widths.append(points)
        return [0.5] * len(points)  # every candidate identical -> elite std = 0

    result = cem.search_unit(3, batch, generations=6, population=8, seed=3)
    assert all(step.sigma >= cem.SIGMA_FLOOR for step in result.history)


def test_samples_stay_inside_the_search_box():
    """A Gaussian proposes anything; a doctrine outside its box may not even
    execute (a negative deque length, a ratio above 1)."""
    def batch(points):
        assert all(0.0 <= v <= 1.0 for point in points for v in point)
        return [sum(point) for point in points]

    cem.search_unit(5, batch, generations=4, population=10, sigma=5.0, seed=4)


def test_doctrine_round_trips_through_the_unit_cube():
    keys = keys_for(None)
    base = Doctrine()
    assert cem.from_unit(base, keys, cem.to_unit(base, keys)) == base


def test_search_doctrine_returns_a_playable_doctrine():
    keys = keys_for("police")

    def batch(candidates):
        return [float(c.gap_window) for c in candidates]  # trivially maximised

    tuned, result = cem.search_doctrine(Doctrine(), keys, batch,
                                        generations=6, population=12, seed=5)
    assert isinstance(tuned.gap_window, int)
    assert tuned.gap_window > Doctrine().gap_window
    assert tuned.w_risk == Doctrine().w_risk, "a police search must not touch thief keys"
    assert len(result.history) == 6
