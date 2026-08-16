"""End-of-game signals that an opponent's dialect does not seal.

The reference protocol carries the thief's capture answer and the survival
claim as plain fields on the next turn message, outside its commitment. We
still act on them - refusing would hang the match - but the cause string
records that the evidence was unsealed, so the distinction survives into the
log, the result artifact and the replay viewer.
"""

from __future__ import annotations

from typing import Any

from ..domain.rules import POLICE, THIEF
from ..domain.scoring import CAPTURE, SURVIVAL


def note_capture_confirmed(engine: Any, cell: list[int]) -> None:
    """Their unsealed `caught: true` - an answer to our claim, or a concession.

    The league kit (SPEC 3.1) separates the two: a cell that echoes what we
    claimed is the co-location shape, while any *other* cell is a rule-46/47
    concession - a barrier on the thief's own cell, or no legal move left. Only
    the thief can see those, so it must say so, and only the thief profits from
    saying so falsely. The kit asks the cop to corroborate a concession against
    its **own** barrier record, never the barrier list the thief reports.

    We corroborate but do not sanction. Both endings still settle CAPTURE, and
    the verdict rides in the cause string into the log, the result and the
    replay - the kit permits this route explicitly ("reported, never a
    unilateral rewrite: the logs decide", rule 35). Refusing a point on our own
    authority mid-league is the more expensive way to be wrong: an honest
    concession we mis-judge costs us 20 that the artifacts would have proven.
    """
    engine._finish(CAPTURE, POLICE,
                   f"claim confirmed at {cell} (unsealed answer"
                   f"{_corroboration(engine, cell)})")


def _corroboration(engine: Any, cell: list[int]) -> str:
    """Read a `caught: true` as answer or concession, and corroborate the latter.

    Silent for an answer, because a claim we made and they confirmed needs no
    second witness here - its cell is checked against their revealed trail at
    the audit, where the trail actually exists.
    """
    if getattr(engine, "role", None) != POLICE:
        return ""
    board = getattr(engine, "board", None)
    if board is None:
        return ""
    position = tuple(cell)
    if position == getattr(engine, "last_claim_cell", None):
        return ""
    if position in board.barriers:
        return ", concession corroborated: our barrier is on that cell"
    if board.is_enclosed(position):
        return ", concession corroborated: our barriers enclose that cell"
    return (", concession NOT corroborated: our barrier record leaves that cell "
            "open and unenclosed")


def note_survival_claimed(engine: Any, kind: str) -> None:
    """Their unsealed win claim; still checked against the agreed threshold."""
    if engine.opp_steps >= engine.shared.survival_threshold:
        engine._finish(SURVIVAL, THIEF,
                       f"{kind} at {engine.opp_steps} steps (unsealed claim)")
    else:
        engine.declare_technical(
            engine.other,
            f"survival claimed at {engine.opp_steps} steps, "
            f"threshold {engine.shared.survival_threshold}")
