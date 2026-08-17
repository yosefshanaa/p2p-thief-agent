"""Where the opponent goes next, given an exact fix on where it just was.

:mod:`..domain.tracking` recovers the opponent's cell from its published scent
field, but a fix is evidence about the *past* - one step old under ``book_v1``,
and always one step older than the decision that has to use it, because the
opponent moves again before we see anything new. The gap between "where it was"
and "where it is" is what this module fills.

The model is deliberately one line of behaviour rather than a policy: an evader
prefers cells that put distance between it and its pursuer, a pursuer prefers
cells that close it. So mass spreads over legal moves weighted by
``bias ** (delta distance to the anchor)``, with ``bias > 1`` for an evader and
``bias < 1`` for a pursuer, and ``bias == 1`` recovering the honest uniform
prior. Both biases are doctrine keys, so the offline search fits them to the
opponents we actually face instead of to an assumption about how they play.

Cheap on purpose: one BFS from the anchor plus a step of redistribution per
turn of lag, on 49 cells. It is called on every turn of every candidate move
in the offline search, which is where a clever model would have been unaffordable.
"""

from __future__ import annotations

from ..domain.board import Board, Cell
from .pathing import bfs_distances

Distribution = dict[Cell, float]


def spread(board: Board, origin: Cell, anchor: Cell, *, steps: int,
           bias: float) -> Distribution:
    """Probability over cells ``steps`` opponent-moves after it stood on ``origin``.

    ``anchor`` is the cell it is reacting to - ours. ``steps`` of 0 is the fix
    itself, which is the whole answer under a scent model that serves after
    emitting.
    """
    current: Distribution = {origin: 1.0}
    if steps <= 0:
        return current
    from_anchor = bfs_distances(board, anchor)
    far = board.size * board.size
    for _ in range(steps):
        nxt: Distribution = {}
        for cell, mass in current.items():
            targets = [cell, *board.open_neighbors(cell)]
            here = from_anchor.get(cell, far)
            weights = [bias ** (from_anchor.get(t, far) - here) for t in targets]
            total = sum(weights) or 1.0
            for target, weight in zip(targets, weights, strict=True):
                nxt[target] = nxt.get(target, 0.0) + mass * weight / total
        current = nxt
    return current


def strike_zone(board: Board, where: Distribution) -> Distribution:
    """Probability that the opponent can *reach* each cell on its next move.

    A thief is not caught by standing where the pursuer is; it is caught by
    standing where the pursuer can step. Summing rather than maximising is
    deliberate - two separate approaches converging on one cell make it more
    dangerous, not equally dangerous.
    """
    out: Distribution = {}
    for cell, mass in where.items():
        for target in [cell, *board.open_neighbors(cell)]:
            out[target] = out.get(target, 0.0) + mass
    return out
