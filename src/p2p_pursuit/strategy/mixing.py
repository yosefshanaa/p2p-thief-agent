"""Mixed move selection: play a distribution, not a function.

Both brains pick their move with a single ``max``/``min`` over a scored list of
candidates, which makes each of them a *pure function of the view*. That is a
real property, not a stylistic one, and it is measured: replayed against the
same pursuer from the same starting cells, our thief produced **six byte-
identical twenty-cell trajectories** in six sub-games. A league match is exactly
that experiment - six sub-games, one constitution, two fixed starting cells that
neither side may vary, because ``thief_start`` and ``cop_start`` are signed terms
of the config both peers hash at Step-0.

An opponent therefore gets up to five more attempts at a line that worked once.
That is not a hypothetical: against uoh-ay26 our thief was taken on (5,5) at
step 10 in all three of the sub-games it played as thief, having reached (5,5)
in four moves every time.

The remedy is the game-theoretic one rather than another weight. A pursuit game
is zero-sum, and in a zero-sum game a deterministic policy is the maximally
exploitable one: an opponent who can predict the evader can cut it off, whereas
against a mixed policy the best it can do is play the distribution. So this
module turns the argmax into a draw from the moves that are *nearly* argmax.

Two properties are deliberate:

* **Free where it matters.** Only moves within ``margin`` of the best are ever
  drawn, so a decisive move - the single step out of a closing strike zone, worth
  several points of ``w_strike`` - is still taken with probability 1. Mixing
  spends nothing on the turns that decide the sub-game and everything on the
  turns that do not, which is exactly where unpredictability is cheap.
* **Off is off.** At ``margin <= 0`` the incumbent selection runs untouched,
  tie-breakers and all. The behaviour is not "the same in expectation"; it is the
  same, which is what makes the term safe to search and the change auditable.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from typing import Any


def _primary(value: Any) -> float:
    """The scalar a move is really ranked by.

    The police scores a tuple - distance first, then tie-breakers - so a margin
    compared against the whole tuple would be comparing lexicographic order to a
    float. Only the leading term is on the scale the doctrine's margin is in.
    """
    return float(value[0] if isinstance(value, tuple) else value)


def choose(moves: Iterable[str], key: Callable[[str], Any], margin: float,
           rng: random.Random, *, prefer: Callable = max) -> str:
    """The best move, or a uniform draw from every move close enough to it.

    ``prefer`` is :func:`max` for the thief (higher score is better) and
    :func:`min` for the police (lower distance is better); ``margin`` is in the
    units of whatever that brain's score is, which is why each role searches its
    own.
    """
    moves = list(moves)
    best = prefer(moves, key=key)
    if margin <= 0:
        return best
    edge = _primary(key(best))
    # `sorted` so the draw depends only on the rng, never on the order the board
    # happened to enumerate legal moves in - the lab and the wire must agree.
    field = sorted(m for m in moves if abs(_primary(key(m)) - edge) <= margin)
    return rng.choice(field) if len(field) > 1 else best
