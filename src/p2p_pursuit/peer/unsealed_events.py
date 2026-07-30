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
    """Their unsealed answer says our capture claim landed."""
    engine._finish(CAPTURE, POLICE, f"claim confirmed at {cell} (unsealed answer)")


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
