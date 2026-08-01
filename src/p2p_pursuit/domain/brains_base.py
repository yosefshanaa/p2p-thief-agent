"""BrainBase plug-in contract (book Appendix F table 22).

The private TOML ``[strategy]`` section selects the brain class per role
(``package.module:Class``); subclasses override ``_pick_move`` (thief) or
``_decide_move`` (police - move *or* barrier). The move is always pure
Python; the view never contains the opponent's true position.
"""

from __future__ import annotations

import importlib
import random
from dataclasses import dataclass

from .belief import BeliefMap
from .board import Board, Cell
from .rules import POLICE, Decision


@dataclass
class BrainView:
    """Local truth only: what one agent legitimately knows when deciding."""

    role: str
    sub_game: int
    step: int
    own_pos: Cell
    board: Board
    belief: BeliefMap
    opp_scent: list[list[float]]
    own_scent: list[list[float]]
    barriers_used: int
    barrier_quota: int
    steps_remaining: int
    survival_threshold: int
    trust: float
    map_area: str
    rng: random.Random
    #: Did this opponent agree that an enclosed thief is captured (book 3.4)?
    #: When they did not, completing an enclosure is a self-inflicted loss: the
    #: evader is sealed into a pocket we cannot enter either, and the sub-game
    #: runs to survival. Measured live 2026-08-01 - 5 points where 20 was on
    #: offer. The squeeze must therefore stop one door short.
    claim_enclosure: bool = True


class BrainBase:
    """Default brain: subclass and override the hooks below."""

    claim_threshold = 0.5  # police: claim capture when belief at own cell reaches this

    def decide(self, view: BrainView) -> Decision:
        return self._decide_move(view) if view.role == POLICE else self._pick_move(view)

    def _pick_move(self, view: BrainView) -> Decision:
        """Thief hook - choose a movement. Default: first legal move."""
        return Decision(move=view.board.legal_moves(view.own_pos)[0])

    def _decide_move(self, view: BrainView) -> Decision:
        """Police hook - choose a movement or a barrier placement."""
        return self._pick_move(view)

    def hint_plan(self, view: BrainView, decision: Decision) -> tuple[str, str]:
        """Return (claimed_region, intent) for the verbal channel. Default: honest."""
        from .hints import region_of

        return region_of(view.own_pos, view.board.size), "truth"

    def should_claim(self, view: BrainView, new_pos: Cell) -> bool:
        """Police only: issue a Capture Claim after landing on ``new_pos``?"""
        belief_here = view.belief.grid[new_pos[0]][new_pos[1]]
        desperate = view.steps_remaining <= 6 and belief_here >= 0.06
        return belief_here >= self.claim_threshold or desperate


def load_brain(spec: str | None, role: str) -> BrainBase:
    """Instantiate the configured brain, or the shipped default for the role."""
    if not spec:
        module = "p2p_pursuit.strategy.police_brain" if role == POLICE else \
            "p2p_pursuit.strategy.thief_brain"
        cls = "PoliceBrain" if role == POLICE else "ThiefBrain"
        spec = f"{module}:{cls}"
    mod_name, _, cls_name = spec.partition(":")
    brain = getattr(importlib.import_module(mod_name), cls_name)()
    if not isinstance(brain, BrainBase):
        raise TypeError(f"{spec} does not subclass BrainBase")
    return brain
