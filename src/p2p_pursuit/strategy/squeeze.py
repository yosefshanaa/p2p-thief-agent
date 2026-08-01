"""The police as "architect of the arena" (book 3.4).

The book is explicit that the barrier quota "is the heart of the police's
strategic challenge", and that the police must "squeeze the thief into a corner
without accidentally blocking its own access routes". Crucially it names a third
capture path most implementations ignore: **a thief with no legal move at all -
every neighbour a barrier or the board edge - is captured**, exactly as if it
had been landed on.

That reframes the arithmetic. Landing on a moving evader is near-impossible
between equal-speed agents, but enclosure is cheap:

* a thief in a corner has 2 exits  -> 2 barriers capture it
* a thief on an edge has 3 exits   -> 3 barriers
* a thief in the open has 4 exits  -> 4 barriers

The catch is that a placement must be within one step of the *police*, and the
thief moves every turn. So the doctrine is not "wall the board", it is: drive
the evader to low-mobility ground, then take its exits one at a time from
close range, always keeping our own path to it open.
"""

from __future__ import annotations

from ..domain.board import Board, Cell
from .pathing import bfs_distances, still_connected

# There is deliberately no "only squeeze when the evader is cornered" gate.
# The placement rule already supplies a strong one - a barrier must go within a
# step of the police, so a door can only be closed from right beside it - and
# every additional threshold measured *worse*: gating on mobility<=3/range<=3
# scored 22%/3% where ungated scores 75%/78%. Restricting the doctrine spends
# the same tempo while forgoing the placements that actually convert.
#: Exit count above which we would decline to squeeze (unbounded: never).
SQUEEZE_MOBILITY = 4
#: Distance beyond which we would decline (unbounded in practice: a placement
#: must be adjacent to us anyway, so this can never be the binding constraint).
SQUEEZE_RANGE = 99


def exits(board: Board, cell: Cell) -> list[Cell]:
    """The evader's legal escape squares from ``cell``."""
    return [n for n in board.neighbors4(cell) if board.is_open(n)]


def placeable(board: Board, own: Cell) -> list[Cell]:
    """Cells the police may bar this turn: its own, or one orthogonal step."""
    return [c for c in [own, *board.neighbors4(own)] if board.is_open(c)]


def squeeze_play(board: Board, own: Cell, evader: Cell, *, quota_left: int,
                 reserve: int, claim_enclosure: bool = True) -> Cell | None:
    """Take one of the evader's exits, if that is worth a forfeited move.

    Returns the cell to bar. Never returns a placement that would cut us off
    from the evader - a wall we cannot cross converts a winning squeeze into a
    stalemate, which is the failure mode the book warns about by name.

    ``claim_enclosure`` is that same warning applied to the *rules* rather than
    the geometry. Sealing the last door only wins if the opponent agrees that an
    enclosed thief is captured; against one that does not, it builds a pocket we
    cannot enter either and hands them survival. Measured live 2026-08-01: we
    barred (6,5) and (5,6), their thief sat in (6,6) for 27 turns, we finished
    outside our own wall, and a capture became 5 points. So when the rule is not
    agreed we stop one door short and take the last exit by standing on it.
    """
    if quota_left <= 0:
        return None
    escape = exits(board, evader)
    # Enclosure is imminent: spend the reserve rather than hoard it.
    if not escape:
        return None
    if not claim_enclosure and len(escape) <= 1:
        return None  # the last door stays open: pin, do not seal
    endgame = len(escape) <= 1
    if quota_left <= reserve and not endgame:
        return None
    if len(escape) > SQUEEZE_MOBILITY:
        return None
    if bfs_distances(board, own).get(evader, 99) > SQUEEZE_RANGE:
        return None
    options = set(placeable(board, own)) & set(escape)
    if not options:
        return None
    # Close the widest door first: the exit opening onto the most room.
    def room(cell: Cell) -> int:
        trial = board.clone()
        trial.add_barrier(cell)
        return len(bfs_distances(trial, evader))

    for cell in sorted(options, key=room):
        if still_connected(board, cell, own, evader):
            return cell
    return None


def squeeze_target(board: Board, own: Cell, evader: Cell) -> Cell | None:
    """Where to stand so the next exit becomes barrable.

    Chasing the evader itself is the wrong aim once it is cornered: we need to
    be adjacent to the door we intend to close, not to the evader.
    """
    escape = exits(board, evader)
    if not escape or len(escape) > SQUEEZE_MOBILITY:
        return None
    reachable = bfs_distances(board, own)

    def widest(cell: Cell) -> tuple[int, int]:
        trial = board.clone()
        trial.add_barrier(cell)
        return (-len(bfs_distances(trial, evader)), reachable.get(cell, 99))

    return min(escape, key=widest)
