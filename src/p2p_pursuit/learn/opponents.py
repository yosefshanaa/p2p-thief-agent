"""Sparring partners: the policies other teams plausibly shipped.

None of these is meant to be strong. They are meant to be *different* - a
doctrine tuned against one evader learns that evader, which is exactly how the
90-98% self-play capture rate coexisted with 0/5 on the wire. Each brain here
is a plain reading of the book that a competent team could have written in an
afternoon, so a doctrine that scores well against all of them is answering a
family of opponents rather than a single fixed point.

The archetypes live in four sibling modules, grouped by what they navigate on
(§3.2 - split, never compress); this module is the single import surface for
all of them, so `learn.opponents.Evader` keeps meaning what it always did.
"""

from __future__ import annotations

from .opponents_base import FAR, _manhattan, _step_toward
from .opponents_evasion import Cager, Evader
from .opponents_scripted import (
    NAJAMJAD_CAGE_BARRIERS,
    NAJAMJAD_CAGE_BARRIERS_FRIENDLY,
    NAJAMJAD_CAGE_MOVES,
    NAJAMJAD_CAGE_MOVES_FRIENDLY,
    Scripted,
    Transcript,
    najamjad_cage,
)
from .opponents_simple import (
    BarrierHappy,
    Camper,
    Greedy,
    Holder,
    Momentum,
    RandomWalker,
)
from .opponents_tracking import Interceptor, Replayer, Sniper

__all__ = [
    "FAR", "NAJAMJAD_CAGE_BARRIERS", "NAJAMJAD_CAGE_BARRIERS_FRIENDLY",
    "NAJAMJAD_CAGE_MOVES", "NAJAMJAD_CAGE_MOVES_FRIENDLY", "BarrierHappy",
    "Cager", "Camper", "Evader", "Greedy", "Holder", "Interceptor", "Momentum",
    "RandomWalker", "Replayer", "Scripted", "Sniper", "Transcript",
    "_manhattan", "_step_toward", "najamjad_cage",
]
