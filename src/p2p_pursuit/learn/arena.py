"""Score a doctrine the way the league scores it: points per sub-game.

Capture rate is the wrong objective. The table pays 20 for a capture as police
but only 5 for surviving, and 10 for surviving as thief against 5 for being
caught, so a doctrine that trades a little capture probability for a lot of
survival can lose the league while winning the metric. Every number this module
reports is therefore in points, and every candidate is played in *both* roles
against every opponent - which is what role alternation does to a match anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..domain.rules import POLICE, THIEF
from ..domain.scoring import CAPTURE, SURVIVAL
from ..peer.local_match import play_sub_game
from ..peer.turn_engine import TurnEngine
from ..shared.config import PeerConfig, SharedConfig, load_shared
from ..strategy.params import Doctrine
from .population import Member, ours

SHARED_PATH = Path("config/police/game.json")
QUIET = PeerConfig(raw={}, group_name="lab", group_id="lab")


@lru_cache(maxsize=1)
def default_shared(path: Path = SHARED_PATH) -> SharedConfig:
    return load_shared(path)


@dataclass
class Score:
    """One doctrine's report card, in league points."""

    points: float = 0.0                       # mean our-points per sub-game
    sub_games: int = 0
    captures_as_police: int = 0
    survivals_as_thief: int = 0
    police_sub_games: int = 0
    thief_sub_games: int = 0
    per_opponent: dict[str, float] = field(default_factory=dict)

    @property
    def capture_rate(self) -> float:
        return self.captures_as_police / max(self.police_sub_games, 1)

    @property
    def survival_rate(self) -> float:
        return self.survivals_as_thief / max(self.thief_sub_games, 1)


def sub_game(shared: SharedConfig, police_brain, thief_brain, seed: int) -> tuple[str, int, int]:
    """Play one sub-game between two brains; return (ending, police, thief) points."""
    police = TurnEngine(POLICE, shared, QUIET, brain=police_brain, seed=seed * 2)
    thief = TurnEngine(THIEF, shared, QUIET, brain=thief_brain, seed=seed * 2 + 1)
    play_sub_game(police, thief)
    ending = police.end.ending if police.end else SURVIVAL
    return (ending, *police.score_table.score(ending))


def score(doctrine: Doctrine, pool: dict[str, Member], seeds: tuple[int, ...],
          shared: SharedConfig | None = None,
          roles: tuple[str, ...] = (POLICE, THIEF)) -> Score:
    """Play the doctrine in the given roles against every opponent on every seed.

    ``roles`` narrows the objective when only half the vector is being searched:
    the thief's points do not move when a police key changes, so including them
    doubles the cost and dilutes the signal the elite selection sees.
    """
    shared = shared or default_shared()
    report = Score()
    for name, member in pool.items():
        earned = played = 0
        for seed in seeds:
            # We play police only against archetypes that are distinctive as
            # thieves, and vice versa - see population.Member.roles.
            if POLICE in roles and THIEF in member.roles:
                ending, police_pts, _ = sub_game(
                    shared, ours(POLICE, doctrine), member.make(THIEF), seed)
                earned, played = earned + police_pts, played + 1
                report.police_sub_games += 1
                report.captures_as_police += ending == CAPTURE
            if THIEF in roles and POLICE in member.roles:
                ending, _, thief_pts = sub_game(
                    shared, member.make(POLICE), ours(THIEF, doctrine), seed + 500_000)
                earned, played = earned + thief_pts, played + 1
                report.thief_sub_games += 1
                report.survivals_as_thief += ending == SURVIVAL
        if not played:
            continue
        report.per_opponent[name] = earned / played
        report.sub_games += played
        report.points += earned
    report.points /= max(report.sub_games, 1)
    return report


#: (doctrine, opponent names, seeds, roles) - every field picklable.
Task = tuple[Doctrine, tuple[str, ...], tuple[int, ...], tuple[str, ...]]


def points_for(task: Task) -> float:
    """The scalar the search maximises, as a worker-process entry point.

    Opponent factories are closures and do not pickle, so the task carries
    *names* and the worker rebuilds the pool on its own side.
    """
    from .population import build

    doctrine, names, seeds, roles = task
    return score(doctrine, build(names), seeds, roles=roles).points
