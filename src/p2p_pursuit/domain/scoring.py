"""Score table - the reward function R, read from the shared constitution.

Endings: capture 20/5, survival 5/10, technical loss 0/0 (both sides zeroed,
so nobody profits from stalling), series tie -> tie_score each (book ch. 3 + 9).
"""

from __future__ import annotations

from dataclasses import dataclass

CAPTURE = "capture"
SURVIVAL = "survival"
TECHNICAL_LOSS = "technical_loss"


@dataclass(frozen=True)
class ScoreTable:
    capture_cop: int
    capture_thief: int
    survival_cop: int
    survival_thief: int
    tie_score: int
    technical_loss: int

    @classmethod
    def from_config(cls, scoring: dict) -> ScoreTable:
        return cls(
            capture_cop=scoring["capture_cop"],
            capture_thief=scoring["capture_thief"],
            survival_cop=scoring["survival_cop"],
            survival_thief=scoring["survival_thief"],
            tie_score=scoring["tie_score"],
            technical_loss=scoring["technical_loss"],
        )

    def score(self, ending: str) -> tuple[int, int]:
        """Return (police_points, thief_points) for a sub-game ending."""
        if ending == CAPTURE:
            return self.capture_cop, self.capture_thief
        if ending == SURVIVAL:
            return self.survival_cop, self.survival_thief
        if ending == TECHNICAL_LOSS:
            return self.technical_loss, self.technical_loss
        raise ValueError(f"unknown ending {ending!r}")
