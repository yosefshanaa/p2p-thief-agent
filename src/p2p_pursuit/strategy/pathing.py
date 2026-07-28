"""Barrier-aware grid search: BFS distances and connectivity (self-trap veto)."""

from __future__ import annotations

from collections import deque

from ..domain.board import Board, Cell

UNREACHABLE = 10_000


def bfs_distances(board: Board, source: Cell) -> dict[Cell, int]:
    """Shortest orthogonal path lengths from ``source`` around barriers."""
    dist = {source: 0}
    queue = deque([source])
    while queue:
        cell = queue.popleft()
        for nxt in board.open_neighbors(cell):
            if nxt not in dist:
                dist[nxt] = dist[cell] + 1
                queue.append(nxt)
    return dist


def distance(board: Board, a: Cell, b: Cell) -> int:
    return bfs_distances(board, a).get(b, UNREACHABLE)


def still_connected(board: Board, hypothetical_barrier: Cell, src: Cell, dst: Cell) -> bool:
    """Self-trap veto: with the extra barrier placed, can ``src`` still reach ``dst``?"""
    trial = board.clone()
    trial.add_barrier(hypothetical_barrier)
    if not trial.on_board(dst) or dst in trial.barriers:
        dst_ok = list(trial.open_neighbors(dst)) if trial.on_board(dst) else []
        return any(n in bfs_distances(trial, src) for n in dst_ok)
    return dst in bfs_distances(trial, src)


def scent_centroid(field: list[list[float]]) -> Cell | None:
    """Mass center of a scent field (rounded to a cell); None when the field is silent."""
    total = sum(map(sum, field))
    if total <= 0:
        return None
    r = sum(i * sum(row) for i, row in enumerate(field)) / total
    c = sum(j * v for row in field for j, v in enumerate(row)) / total
    return (round(r), round(c))
