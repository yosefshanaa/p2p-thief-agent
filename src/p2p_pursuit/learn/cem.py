"""Cross-entropy method: the optimiser behind both the tuner and the cloner.

CEM rather than a gradient method because the objective is a discrete game with
no derivative, and rather than a grid sweep because 23 dimensions is far past
what sweeping reaches. It is the policy-search family of reinforcement
learning: sample policies, keep the elite, refit the sampling distribution.

Three details do all the work of making it honest on a noisy objective:

* **Common random numbers.** Every candidate in a generation is scored on the
  *same* seeds, so comparing them is not comparing luck.
* **Elitism.** The incumbent mean is re-scored every generation and competes,
  so a lucky elite set cannot walk the distribution downhill.
* **A variance floor.** Without it the distribution collapses onto the first
  plausible basin after three or four generations and stops searching.

Everything is searched in the unit cube, so one sigma is meaningful across axes
whose natural units differ by three orders of magnitude.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..strategy.params import SPACE, Doctrine, from_vector, to_vector

SIGMA_FLOOR = 0.03
Batch = Callable[[list[list[float]]], list[float]]


@dataclass
class Step:
    generation: int
    best: float
    mean_elite: float
    sigma: float


@dataclass
class Result:
    best: list[float]
    best_score: float
    baseline: float
    history: list[Step]


def search_unit(dim: int, evaluate: Batch, *, start: Sequence[float] | None = None,
                generations: int = 8, population: int = 24, elite_frac: float = 0.25,
                sigma: float = 0.22, seed: int = 0) -> Result:
    """Maximise ``evaluate`` over the unit cube; it scores a whole generation."""
    rng = random.Random(seed)
    mean = list(start) if start is not None else [0.5] * dim
    spread = [sigma] * dim
    elite_n = max(2, min(population - 1, round(population * elite_frac)))
    best, best_score, baseline = list(mean), None, None
    history: list[Step] = []
    for generation in range(1, generations + 1):
        # The incumbent goes in first: it is the elitism, and re-scoring it on
        # this generation's seeds is what keeps the comparison fair.
        points = [list(mean)]
        points += [[rng.gauss(m, s) for m, s in zip(mean, spread, strict=True)]
                   for _ in range(population - 1)]
        points = [[min(max(v, 0.0), 1.0) for v in point] for point in points]
        scores = evaluate(points)
        baseline = scores[0] if baseline is None else baseline
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        elite = ranked[:elite_n]
        if best_score is None or scores[ranked[0]] > best_score:
            best, best_score = points[ranked[0]], scores[ranked[0]]
        mean = [sum(points[i][d] for i in elite) / elite_n for d in range(dim)]
        spread = [max(SIGMA_FLOOR, _std([points[i][d] for i in elite])) for d in range(dim)]
        history.append(Step(generation=generation, best=scores[ranked[0]],
                            mean_elite=sum(scores[i] for i in elite) / elite_n,
                            sigma=sum(spread) / len(spread)))
    return Result(best=best, best_score=best_score or 0.0,
                  baseline=baseline or 0.0, history=history)


def to_unit(doctrine: Doctrine, keys: tuple[str, ...]) -> list[float]:
    """Map a doctrine onto [0, 1] per axis using its declared search box."""
    out = []
    for key, value in zip(keys, to_vector(doctrine, keys), strict=True):
        low, high = SPACE[key][0], SPACE[key][1]
        out.append((value - low) / (high - low))
    return out


def from_unit(base: Doctrine, keys: tuple[str, ...], unit: Sequence[float]) -> Doctrine:
    raw = []
    for key, value in zip(keys, unit, strict=True):
        low, high = SPACE[key][0], SPACE[key][1]
        raw.append(low + value * (high - low))
    return from_vector(base, keys, raw)


def search_doctrine(base: Doctrine, keys: tuple[str, ...],
                    evaluate: Callable[[list[Doctrine]], list[float]],
                    **kwargs) -> tuple[Doctrine, Result]:
    """CEM over the named doctrine keys, starting from the shipped values."""

    def batch(points: list[list[float]]) -> list[float]:
        return evaluate([from_unit(base, keys, point) for point in points])

    result = search_unit(len(keys), batch, start=to_unit(base, keys), **kwargs)
    return from_unit(base, keys, result.best), result


def _std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
