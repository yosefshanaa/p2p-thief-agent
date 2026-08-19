"""Doctrine parameters: the one tunable vector both brains read.

Every constant that was calibrated by measurement now lives here instead of in
the brain that consumes it, for one reason: an offline policy search
(``learn/``) can only optimise what it can address. The defaults below *are*
the shipped v5 doctrine, so a checkout with no ``config/doctrine.json`` plays
exactly as it did before this module existed - the file is an override, never a
requirement.

Freezing matters more than tuning. A counted match must play a *fixed* vector,
committed alongside the code, because the league seals each sub-game against a
``github_commit`` and a match that silently retunes itself is not reproducible
for the audit. So: search offline, write the winner to ``config/doctrine.json``,
commit it, then play.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path

#: Resolved from the package, not the process's working directory. A tuned file
#: that fails to load does not raise - it silently plays a different, weaker
#: policy - so the one thing that must not depend on where `peer` was launched
#: from is which doctrine it plays.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = REPO_ROOT / "config" / "doctrine.json"
#: A doctrine is tuned against one *scent physics*. Negotiating a different model
#: with an opponent therefore changes which tuned vector is correct, and playing
#: the wrong one is silent: it does not fail, it just plays worse (measured
#: 2026-08-09 - the v5 vector loses two thirds of its captures under
#: `registered_v3`). So the path is deployment-time, beside the model itself.
DOCTRINE_PATH_VAR = "P2P_DOCTRINE"


def default_path() -> Path:
    override = (os.environ.get(DOCTRINE_PATH_VAR) or "").strip()
    return Path(override) if override else DEFAULT_PATH

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Doctrine:
    """Both doctrines as one vector. Field names are the search-space keys."""

    # -- police: thresholds are ratios of a rolling peak, never absolutes
    peak_window: int = 12
    gap_window: int = 4
    kill_shot_ratio: float = 0.85
    seal_ratio: float = 0.60
    seal_distance: int = 3
    endgame_reserve: int = 2
    belief_floor: float = 0.22
    police_fresh_min: float = 0.7
    claim_threshold: float = 0.15
    police_truth_rate: float = 0.20
    #: Least probability that a one-step move lands on the thief before we spend
    #: the move on it rather than on position. The pounce is what converts a
    #: scent fix into points: of 76 capture chances in the played archive we
    #: took 11, and 27 of the misses were spent placing a barrier from a cell
    #: adjacent to the thief. A barrier forfeits the move; a pounce is the move.
    pounce_floor: float = 0.18
    #: How much more likely the thief is to take a cell one step further from us
    #: than one step nearer. 1.0 is the uniform prior over its legal moves.
    flee_bias: float = 1.8
    #: Weight on shrinking the thief's half of the board (a Voronoi split), as
    #: against simply closing the distance. Pure distance is a tail chase: the
    #: freshest evidence names where it *was*, so an equal-speed pursuer aiming
    #: there holds the gap and never closes it - measured over the three police
    #: sub-games of the counted match vs gal-roy1, the gap sat at 2 for 45 of 102
    #: turns, reached 1 exactly 3 times, and produced no capture chance at all.
    w_cut: float = 0.35
    # -- thief: a weighted score over one-step candidates
    w_mobility: float = 0.5
    w_mobility2: float = 0.25
    #: Cells we reach strictly before the pursuer does - the room we actually
    #: own, not the exits we happen to touch. `w_mobility`/`w_mobility2` are
    #: 1- and 2-ply openness, and both score a pocket as roomy right up to the
    #: turn its mouth is sealed: measured vs orcai-mj, our thief died at (5,6)
    #: or (6,6) in nine consecutive sub-games across two doctrines and three
    #: seeds, always in a pocket whose only exits the pursuer already owned.
    w_territory: float = 0.15
    #: Below `trap_floor` owned cells we are in a pocket, and the penalty scales
    #: with how far below - but only while the pursuer still holds the barrier
    #: quota to seal it with, since an empty quota cannot close a mouth.
    trap_floor: int = 10
    w_trap: float = 1.2
    w_centroid: float = 0.4
    w_risk: float = 3.0
    w_lead_risk: float = 1.5
    w_trail: float = 0.7
    stay_penalty: float = 1.2
    corner_penalty: float = 0.5
    juke_penalty: float = 0.6
    juke_range: int = 3
    thief_fresh_min: float = 0.7
    thief_truth_rate: float = 0.15
    lie_candidates: int = 3
    #: Mirror of `flee_bias`: how much more likely the pursuer is to take a cell
    #: one step *nearer* to us. Below 1.0 because a pursuer closes.
    chase_bias: float = 0.55
    #: Penalty on stepping back onto the cell we just left. The police learned
    #: this in v4 - 28% of its moves were A->B->A step-backs - and the thief
    #: never did, while `juke_penalty` actively pushes the other way by taxing a
    #: repeated move. Measured against uoh-ay26: our thief oscillated around
    #: (5,5) for ten straight turns, STAY / off / back / STAY / off / back, while
    #: their police walked a monotone staircase from distance 7 to 0 - and on the
    #: final turn stepped back ONTO (5,5) as the police arrived there. The same
    #: cell, the same way, in all three thief sub-games.
    #:
    #: DEFAULT 0 - the diagnosis is evidence, the remedy is not. The arena cannot
    #: see this failure at all (our thief survives it 100% while the real team
    #: took it 3 times out of 3), so it cannot validate a fix for it either; asked
    #: anyway, it prefers 0.0 to every positive value by about a sub-game. So the
    #: term ships addressable and off, rather than shipping a guess that the only
    #: measurement available says is worse. Turn it on when a sparring partner
    #: exists that can actually punish an oscillating evader.
    backtrack_penalty: float = 0.0
    #: Penalty on ending our move inside the pursuer's next-step reach. This is
    #: the term the thief never had: across the archive our thief finished its
    #: move inside that reach 43 times in 35 sub-games and was taken 14 times,
    #: including both losses to gal-roy1, where it stepped to a cell orthogonally
    #: adjacent to a pursuer whose exact cell its own scent feed was carrying.
    w_strike: float = 4.0


#: Fields the offline search is NOT allowed to touch, and why.
#:
#: An optimiser tunes only what its objective can punish. These three govern the
#: *deception* channel, and swapping the whole set between its designed and its
#: searched values moves the outcome by 42-46 captures out of 80 - inside the
#: noise. Only one pool member reads hints at all (`mirror`, our own brain), and
#: even it does not try to *invert* a lie, so the objective cannot tell a safe
#: deception policy from an exploitable one.
#:
#: Left free, the search duly set `lie_candidates` to 1 - which picks the single
#: furthest stale cell and re-creates exactly the decodable lie v4 removed: we
#: transmit the scent field, so any deterministic function of it is recomputable
#: by the opponent, and a lie an opponent can invert is an admission of where we
#: are not. It gained nothing measurable and risked everything against a team
#: that actually models us. Caught by test_brains_v4, not by inspection.
#:
#: These stay at their designed values until the pool contains an opponent that
#: can exploit them; the honest fix is a better sparring partner, not a bound.
UNSEARCHABLE = ("lie_candidates", "police_truth_rate", "thief_truth_rate")

#: name -> (low, high, integral). Bounds are the *search* box, not assertions:
#: they keep the sampler inside values the brains can still execute, and every
#: default sits strictly inside its own box so the search can move either way.
SPACE: dict[str, tuple[float, float, bool]] = {
    "peak_window": (4, 24, True),
    "gap_window": (2, 8, True),
    "kill_shot_ratio": (0.50, 1.00, False),
    "seal_ratio": (0.20, 0.95, False),
    "seal_distance": (1, 5, True),
    "endgame_reserve": (0, 6, True),
    "belief_floor": (0.02, 0.40, False),
    # Capped at the lowest ceiling any negotiated model can serve, not at the
    # kernel's centre. `book_v1` serves before its own emission so its field
    # tops out at 0.81, and `subtractive_chebyshev_v1` at 0.80 - so the search's
    # old ceiling of 0.90 let it pick a threshold no field can ever cross. It
    # did: the shipped vector carried 0.849118, which switched the whole trail
    # branch off for every book_v1 match we have played, silently, because the
    # objective cannot see a feature that never fires. Measured in the lab, the
    # police's trail test fired 0 times in 2,629 turns.
    "police_fresh_min": (0.30, 0.80, False),
    "claim_threshold": (0.03, 0.50, False),
    "pounce_floor": (0.02, 0.60, False),
    "flee_bias": (0.80, 4.00, False),
    "w_cut": (0.0, 2.0, False),
    "w_mobility": (0.0, 2.0, False),
    "w_mobility2": (0.0, 1.5, False),
    "w_territory": (0.0, 1.0, False),
    "trap_floor": (0, 24, True),
    "w_trap": (0.0, 6.0, False),
    "w_centroid": (0.0, 1.5, False),
    "w_risk": (0.0, 8.0, False),
    "w_lead_risk": (0.0, 5.0, False),
    "w_trail": (0.0, 1.0, False),
    "stay_penalty": (0.0, 4.0, False),
    "corner_penalty": (0.0, 3.0, False),
    "juke_penalty": (0.0, 3.0, False),
    "juke_range": (1, 6, True),
    "thief_fresh_min": (0.30, 0.80, False),  # same dead-threshold cap as the police's
    "chase_bias": (0.20, 1.20, False),
    # Floor below zero deliberately: the default is 0 and the invariant is that
    # every default sits STRICTLY inside its box, so the search can move in both
    # directions. A negative value is meaningful rather than a fudge - it says
    # returning to the cell you just left is actively preferred, which is what an
    # evader shadowing a fixed patrol route would want.
    "backtrack_penalty": (-2.0, 5.0, False),
    "w_strike": (0.0, 10.0, False),
}

#: Which half of the vector each role reads. Spelled out rather than derived
#: from a name prefix: the prefix rule silently filed every new key under the
#: thief, so a `--role police` search would have left three police keys at their
#: defaults while reverting them in the thief's file.
POLICE_KEYS = ("peak_window", "gap_window", "kill_shot_ratio", "seal_ratio",
               "seal_distance", "endgame_reserve", "belief_floor", "police_fresh_min",
               "claim_threshold", "pounce_floor", "flee_bias", "w_cut")
THIEF_KEYS = tuple(k for k in SPACE if k not in POLICE_KEYS)


def keys_for(role: str | None) -> tuple[str, ...]:
    """Search only the half of the vector that the given role actually reads."""
    if role == "police":
        return POLICE_KEYS
    if role == "thief":
        return THIEF_KEYS
    return tuple(SPACE)


def to_vector(doctrine: Doctrine, keys: tuple[str, ...]) -> list[float]:
    return [float(getattr(doctrine, k)) for k in keys]


#: Float fields are rounded here, which keeps a tuned file readable and makes
#: the unit-cube round trip exact - the search re-scores its own incumbent every
#: generation, so a 1e-16 drift would quietly make that a different candidate.
PRECISION = 6


def from_vector(base: Doctrine, keys: tuple[str, ...], vector: list[float]) -> Doctrine:
    """Rebuild a doctrine from a search point, clamped and rounded to the space."""
    patch = {}
    for key, raw in zip(keys, vector, strict=True):
        low, high, integral = SPACE[key]
        value = min(max(raw, low), high)
        patch[key] = int(round(value)) if integral else round(value, PRECISION)
    return replace(base, **patch)


def loads(text: str) -> Doctrine:
    """Parse a tuned vector, ignoring keys this version no longer has."""
    raw = json.loads(text)
    known = {k: v for k, v in raw.items() if k in SPACE}
    return from_vector(Doctrine(), tuple(known), [float(v) for v in known.values()])


def save(doctrine: Doctrine, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(doctrine), indent=2) + "\n", encoding="utf-8")


@lru_cache(maxsize=4)
def active(path: Path | None = None) -> Doctrine:
    """The doctrine this process plays: the tuned file if present, else v5.

    Announced at load, because "which policy am I actually running" is not
    something a league match should have to infer from how it played.
    """
    path = path or default_path()
    if not path.exists():
        log.info("doctrine: shipped defaults (no %s)", path)
        return Doctrine()
    doctrine = loads(path.read_text(encoding="utf-8"))
    changed = sum(getattr(doctrine, k) != getattr(Doctrine(), k) for k in SPACE)
    log.info("doctrine: tuned from %s (%d of %d fields differ from the defaults)",
             path, changed, len(SPACE))
    return doctrine
