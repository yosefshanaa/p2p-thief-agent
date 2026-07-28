"""Hint-trust model: the unforgeable scent field is the judge of the verbal channel.

Implements the book's lie-detection doctrine (ch. 4.4): a hint whose region
holds no scent mass while the trail is strong elsewhere is a caught lie -
trust drops hard; corroboration earns it back slowly.
"""

from __future__ import annotations

from dataclasses import dataclass

CONTRADICTED = "contradicted"
CORROBORATED = "corroborated"
NEUTRAL = "neutral"


@dataclass
class TrustModel:
    value: float = 0.5
    floor: float = 0.05

    def judge(self, region_scent_mass: float, max_tau: float) -> str:
        """Compare the hinted region against the scent evidence and update trust."""
        if max_tau < 0.5:  # trail too faint to testify either way
            return NEUTRAL
        if region_scent_mass < 0.1:
            self.value = max(self.floor, self.value * 0.5)
            return CONTRADICTED
        if region_scent_mass > 0.5:
            self.value = min(1.0, self.value + 0.1)
            return CORROBORATED
        return NEUTRAL
