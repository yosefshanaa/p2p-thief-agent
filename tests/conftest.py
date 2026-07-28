"""Shared fixtures: fast in-memory configs and scripted brains."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2p_pursuit.domain.brains_base import BrainBase
from p2p_pursuit.domain.crypto import digest
from p2p_pursuit.domain.rules import Decision
from p2p_pursuit.shared.config import PeerConfig, SharedConfig

BASE = Path(__file__).resolve().parent.parent


def make_shared(**overrides) -> SharedConfig:
    raw = json.loads((BASE / "config" / "police" / "game.json").read_text())
    for dotted, value in overrides.items():
        section, key = dotted.split(".")
        raw[section][key] = value
    return SharedConfig(raw=raw, sha256=digest(raw))


def make_peer(role: str = "police", **kw) -> PeerConfig:
    return PeerConfig(raw={}, group_name=f"team-{role}", group_id=f"team-{role}",
                      members=["111", "222"], repos={"cop": "https://x/c", "thief": "https://x/t"},
                      **kw)


class ScriptedBrain(BrainBase):
    """Plays a fixed move list, then STAYs; used to force exact scenarios."""

    claim_threshold = 2.0  # never claims unless told

    def __init__(self, moves: list[Decision] | None = None, claim_always: bool = False) -> None:
        self.moves = list(moves or [])
        self.claim_always = claim_always

    def _pick_move(self, view) -> Decision:
        return self.moves.pop(0) if self.moves else Decision(move="STAY")

    def should_claim(self, view, new_pos) -> bool:
        return self.claim_always


@pytest.fixture
def shared() -> SharedConfig:
    return make_shared()


@pytest.fixture
def fast_shared() -> SharedConfig:
    """A short game for protocol tests (dev-only values, not league-legal)."""
    return make_shared(**{"movement_and_barriers.max_moves": 6,
                          "movement_and_barriers.survival_threshold": 6,
                          "network_and_league.num_games": 1})
