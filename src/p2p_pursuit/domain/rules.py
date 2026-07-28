"""Move legality and application - the shared physics contract.

The exact same validator judges our own brain's output (safe fallback) and
the opponent's revealed moves at audit time: no external judge exists, so
each peer enforces the physics itself (book ch. 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from .board import MOVES, Board, Cell, target_of

POLICE = "police"
THIEF = "thief"
ROLES = (POLICE, THIEF)


@dataclass(frozen=True)
class Decision:
    """A brain's choice for one step: a move, or a barrier placement (police only).

    Placing a barrier forfeits movement, so ``barrier`` implies ``move == "STAY"``.
    """

    move: str = "STAY"
    barrier: Cell | None = None


def validate(
    board: Board, role: str, pos: Cell, decision: Decision, barriers_used: int, quota: int
) -> str | None:
    """Return None when legal, else a human-readable violation reason."""
    if decision.move not in MOVES:
        return f"unknown move {decision.move!r} (diagonals do not exist)"
    if decision.barrier is not None:
        if role != POLICE:
            return "only the police may place barriers"
        if decision.move != "STAY":
            return "a barrier placement forfeits movement (move must be STAY)"
        if barriers_used >= quota:
            return f"barrier quota exhausted ({quota})"
        cell = decision.barrier
        if not board.on_board(cell):
            return f"barrier target {cell} off board"
        if cell in board.barriers:
            return f"cell {cell} already barred"
        if cell != pos and cell not in board.neighbors4(pos):
            return f"barrier target {cell} not own or orthogonally adjacent cell"
        return None
    tgt = target_of(pos, decision.move)
    if not board.on_board(tgt):
        return f"move {decision.move} leaves the board from {pos}"
    if tgt in board.barriers:
        return f"move {decision.move} enters barrier at {tgt}"
    return None


def apply_decision(board: Board, pos: Cell, decision: Decision) -> Cell:
    """Apply a *validated* decision: mutate the board on barrier, return the new position."""
    if decision.barrier is not None:
        board.add_barrier(decision.barrier)
        return pos
    return target_of(pos, decision.move)


def safe_decision(board: Board, role: str, pos: Cell, barriers_used: int, quota: int,
                  wanted: Decision) -> Decision:
    """Never forfeit on our own brain bug: fall back to the first legal move."""
    if validate(board, role, pos, wanted, barriers_used, quota) is None:
        return wanted
    for move in board.legal_moves(pos):
        candidate = Decision(move=move)
        if validate(board, role, pos, candidate, barriers_used, quota) is None:
            return candidate
    return Decision(move="STAY")
