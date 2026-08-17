"""The sparring pool: named opponent archetypes, ours included.

Each member declares *which roles it is an archetype for*, and that is not
bookkeeping - it is the objective. Several archetypes are only distinctive on
one side: ``barrier`` is a police doctrine whose thief is a plain gradient, and
``hound`` chases the pheromone trail, which as an evader is indistinguishable
from fleeing the belief peak. Listing them in both roles anyway would score our
police against the same greedy evader three times out of eight and quietly
triple its weight in the search - the exact over-fitting this pool exists to
prevent. Measured: as thief, ``greedy``/``hound``/``barrier`` play a byte-
identical trajectory; as police, ``greedy``/``holder`` do.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..domain.brains_base import BrainBase
from ..domain.rules import POLICE, THIEF
from ..strategy.params import REPO_ROOT, Doctrine
from .opponents import BarrierHappy, Camper, Greedy, Holder, Momentum, RandomWalker

Factory = Callable[[str], BrainBase]
#: Package-relative, like the doctrine: a clone directory that fails to resolve
#: does not raise - the pool silently loses every real opponent in it and the
#: search goes back to answering archetypes we invented.
CLONE_DIR = REPO_ROOT / "config" / "opponents"
BOTH = (POLICE, THIEF)


@dataclass(frozen=True)
class Member:
    """One archetype, and the roles in which it is genuinely distinct."""

    make: Factory
    roles: tuple[str, ...] = BOTH


def ours(role: str, doctrine: Doctrine | None = None) -> BrainBase:
    """Our own shipped doctrine - the self-play member of the pool."""
    from ..strategy.police_brain import PoliceBrain
    from ..strategy.thief_brain import ThiefBrain

    return ThiefBrain(doctrine) if role == THIEF else PoliceBrain(doctrine)


BUILTIN: dict[str, Member] = {
    "random": Member(lambda role: RandomWalker()),
    "momentum": Member(lambda role: Momentum()),
    "greedy": Member(lambda role: Greedy(flee=role == THIEF)),
    "hound": Member(lambda role: Greedy(flee=False, use_trail=True), roles=(POLICE,)),
    "noisy": Member(lambda role: Greedy(flee=role == THIEF, jitter=0.25)),
    "barrier": Member(lambda role: BarrierHappy(), roles=(POLICE,)),
    "holder": Member(lambda role: Holder(), roles=(THIEF,)),
    "camper": Member(lambda role: Camper(), roles=(THIEF,)),
    "mirror": Member(ours),
}

DEFAULT_POOL = tuple(BUILTIN)


def clone_factories(directory: Path = CLONE_DIR) -> dict[str, Member]:
    """Every opponent cloned from a played match, keyed by team name.

    A clone plays only the roles it was actually observed in: fitting nothing
    would leave an all-zero weight vector, which is not a neutral opponent but
    a degenerate one that always takes the same move.
    """
    from .clone_fit import ClonedBrain

    found: dict[str, Member] = {}
    if not directory.exists():
        return found
    for path in sorted(directory.glob("*.json")):
        weights = {role: dict(w)
                   for role, w in json.loads(path.read_text(encoding="utf-8"))["weights"].items()}
        if not weights:
            continue
        found[f"clone:{path.stem}"] = Member(
            make=lambda role, w=weights: ClonedBrain(w.get(role, {})),
            roles=tuple(weights))
    return found


def path_factories(directory: Path = CLONE_DIR) -> dict[str, Member]:
    """Opponents that replay a recorded trajectory, keyed ``path:<team>``.

    A fitted clone and a replayed path answer different questions, and against a
    deterministic opponent only the second one is honest: our shipped doctrine
    catches gal-roy1's *clone* 83% of the time in simulation and caught the team
    itself 0 times in 9 live sub-games. The clone is a reactive imitation at 78%
    move agreement, so it wanders where the original never does.

    Kept in a `paths/` subdirectory because `clone_factories` globs this one for
    weight files and would raise on a script.
    """
    from .opponents import Scripted

    found: dict[str, Member] = {}
    for path in sorted((directory / "paths").glob("*.json")):
        roles = json.loads(path.read_text(encoding="utf-8")).get("roles", {})
        scripts = {role: tuple(moves) for role, moves in roles.items() if moves}
        if not scripts:
            continue
        found[f"path:{path.stem}"] = Member(
            make=lambda role, s=scripts: Scripted(s[role]),
            roles=tuple(scripts))
    return found


def build(names: tuple[str, ...] | None = None,
          directory: Path = CLONE_DIR) -> dict[str, Member]:
    """Resolve pool names to members; ``None`` means everything available."""
    available = {**BUILTIN, **clone_factories(directory), **path_factories(directory)}
    if names is None:
        return available
    missing = [n for n in names if n not in available]
    if missing:
        raise KeyError(f"unknown opponents {missing}; have {sorted(available)}")
    return {n: available[n] for n in names}
