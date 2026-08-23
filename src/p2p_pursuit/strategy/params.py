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
    #: `peak_window` is the rolling window `_barrier_play` compares against, and
    #: it is INERT: measured 2026-08-23 at 4, 7, 10 and 14 over 2208 sub-games
    #: per value, every score identical to the digit. Left addressable rather
    #: than deleted, but do not read a searched value for it as evidence.
    peak_window: int = 12
    #: How many turns of pursuit `_evading` looks back over before it will
    #: believe the thief is running - and therefore before the squeeze may
    #: start. The single most valuable integer in this vector, and every shipped
    #: file had it wrong.
    #:
    #: `_evading` fires only when `len(self._gaps) == self._gaps.maxlen`, so
    #: this is both the amount of history required and the age of the gap being
    #: compared against. Shipped at 8 - the top of its own search box - the
    #: squeeze started too late to ever start. Measured 2026-08-23 on fresh
    #: seeds, 3312 sub-games per value:
    #:
    #:   subtractive   8 -> 6   18.315 -> 19.215, and `recorded:vibecode` (the
    #:                          team that beat our police 0/3 in three
    #:                          friendlies) goes 25/240 -> 240/240
    #:   registered    7 -> 5   19.342 -> 19.527
    #:   orcai-mj      7 -> 3   18.555 -> 19.176
    #:   book_v1       already 3, which measured best
    #:
    #: Too small is a real cost, not a free win: at 2 the test fires on two
    #: turns of noise and the police squeezes where a plain chase would have
    #: caught it, which is the 25/30 -> 20/30 regression `_decide_move`
    #: describes. The curve has a genuine interior optimum and every physics
    #: puts it in a different place.
    gap_window: int = 4
    kill_shot_ratio: float = 0.85
    seal_ratio: float = 0.60
    seal_distance: int = 3
    endgame_reserve: int = 2
    belief_floor: float = 0.22
    police_fresh_min: float = 0.7
    #: Belief on our own cell before we issue a capture claim, in the half of
    #: the league that does NOT play `always_claim`. A claim names our cell and
    #: is simply answered, so claiming early costs information and nothing else
    #: - and half the contracts we have signed claim on every single turn.
    #:
    #: Swept by hand 2026-08-23, full pool, 40 seeds x 6 windows on fresh seeds.
    #: Under `subtractive_chebyshev_v1` the shipped 0.291 was far too high:
    #: 0.04, 0.08 and 0.12 are a flat plateau at 19.168/19.168/19.166 against
    #: 18.962, paired 31 better and 2 worse. 0.12 is the top of that plateau, so
    #: it takes the same points while claiming on the fewest turns. The other
    #: two physics measured a tie and were left alone (registered 19.486 vs
    #: 19.476; book 19.188 vs 19.155), which is the usual pattern here - a term
    #: is worth different amounts under different scent models.
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
    #:
    #: Fitted against the archive it is 1.05, not 1.8 - and the value it *is*
    #: calibrated to belongs to the reference kit's own bot, which fits 3.90
    #: while every real team we have played fits 1.00-1.15. That is a genuine
    #: miscalibration of the *prediction* and it does not transfer to the
    #: policy: set to the fitted value it converts no additional capture chance
    #: in the played archive and costs the lab nine points of capture rate
    #: (0.812 -> 0.725), because this weight is doing a pursuit job - lead the
    #: quarry - and not only a forecasting one. Left where the play measures it.
    #:
    #: And the play now measures it higher, under ONE physics. Coordinate
    #: descent 2026-08-23 found this completely inert under
    #: `subtractive_chebyshev_v1` and live under `book_v1` - which is exactly
    #: what the "prediction" reading predicts: with an invertible field the
    #: pursuer has the thief's cell and has nothing to forecast, while book's
    #: fix is a step stale. So `doctrine.json` moved 2.757 -> 3.6 (19.185 ->
    #: 19.266 pts/sub-game, 30 better and 10 worse paired, `evader` 191/240 ->
    #: 224/240) and the subtractive file did not move at all. 3.3/3.6/3.9 are a
    #: plateau; 3.6 was taken because 3.9 sits on the search bound.
    flee_bias: float = 1.8
    #: Weight on the chance a candidate cell is the thief's, scored as a term in
    #: the pursuit rather than as an override of it.
    #:
    #: `pounce_floor` gates an early return, so lowering it does not merely take
    #: more shots - it stops `_pursue` running at all, and with it the
    #: territory, anti-camp, anti-dither and mixing rules. Measured: at floor
    #: 0.20 the archive converts exactly as many chances as at 0.262 while the
    #: lab's capture rate falls 0.812 -> 0.704, and by 0.04 it reaches 0.567.
    #: Priced as a term instead, on the same scale as distance, one unit reads
    #: "a cell that certainly holds the thief is worth one step of ground" - a
    #: tie-break, which is all a sub-threshold chance should ever be. That takes
    #: the archive from 26 of 76 chances converted to 29, and won on all FIVE
    #: independent seed sets it was scored over - none of them used to pick it:
    #: +0.023 capture rate over 2480 police sub-games, about two standard
    #: errors, so real and small. A no-op under any lag-0 physics, where
    #: `_where` is a delta on the fix and the pounce has already spent it or
    #: cannot reach it - measured identical to three decimals over 640.
    w_pounce: float = 1.0
    #: Weight on shrinking the thief's half of the board (a Voronoi split), as
    #: against simply closing the distance. Pure distance is a tail chase: the
    #: freshest evidence names where it *was*, so an equal-speed pursuer aiming
    #: there holds the gap and never closes it - measured over the three police
    #: sub-games of the counted match vs gal-roy1, the gap sat at 2 for 45 of 102
    #: turns, reached 1 exactly 3 times, and produced no capture chance at all.
    w_cut: float = 0.35
    #: How far below the best a move may score and still be drawn at random -
    #: the police's half of the mixed policy (see :mod:`.mixing`). In cells of
    #: BFS distance, because that is the leading term of its move score.
    police_mix_margin: float = 0.0
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
    #: Weight on the room we could still be sealed into *alone* - the only term
    #: with a gradient while a wall is being built. `w_trap` above is reactive
    #: and fires once the pocket has already closed; on najamjad's cage that was
    #: measured to be seven turns after the last step from which the gap was
    #: reachable. Default 0.0: it is a real per-turn cost (a pairwise scan over
    #: the seam) and it is the search's job to decide whether it earns its keep.
    w_lifeboat: float = 0.0
    #: Weight on being on the wall-builder's side of a forming wall. The only
    #: anticipatory term whose signal arrives before the escape expires: three
    #: collinear barriers on their turn 7 against a turn-9 deadline. Default 0.0
    #: - off until it is measured to earn its place.
    w_wall_side: float = 0.0
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
    #:
    #: The subtractive file carried a searched 3.297 and now carries **1.0**,
    #: which is a deliberate compromise rather than the argmax. Coordinate
    #: descent over the whole thief vector (2880 sub-games per trial) found this
    #: the ONLY key with anything to say, and 0.0 / 0.5 / 1.0 all measure the
    #: same 9.930 against 3.297's 9.878 - 44 better and **0 worse** paired, with
    #: our thief's survivals against `mirror` going 217/288 to 288/288. 1.0 is
    #: the top of that flat region, so it takes the whole gain while still
    #: pricing the exact step-back the archive recorded.
    #:
    #: Why the high value cost anything at all: `w_grave` now prices the cell a
    #: previous window died on, which is precisely what the uoh-ay26 death was.
    #: A heavy blanket tax on *every* return then double-charges the one cell
    #: that matters and overcharges the forty-eight that do not.
    backtrack_penalty: float = 0.0
    #: Penalty on ending our move inside the pursuer's next-step reach. This is
    #: the term the thief never had: across the archive our thief finished its
    #: move inside that reach 43 times in 35 sub-games and was taken 14 times,
    #: including both losses to gal-roy1, where it stepped to a cell orthogonally
    #: adjacent to a pursuer whose exact cell its own scent feed was carrying.
    w_strike: float = 4.0
    #: The thief's half of the mixed policy (see :mod:`.mixing`), in units of its
    #: weighted move score. This is the term that answers "we played the same
    #: game six times": our evader is a pure function of the view, and replayed
    #: against one pursuer it produced six identical trajectories, so an opponent
    #: that beats it once beats it in every remaining sub-game of the match.
    #:
    #: DEFAULT 0, on the measurement rather than on principle - but the shipped
    #: subtractive file now carries 0.25, and the reason the older measurement
    #: read the other way is that the POLICE changed underneath it. "Survival is
    #: 0/40 at margins 0, 0.15, 0.40 and 1.00" was taken against a pursuer whose
    #: `gap_window` was pinned at the top of its box, so it never squeezed in
    #: time; against one that does, unpredictability finally buys something -
    #: 9.895 against 9.826, and our thief's survivals against `mirror` go
    #: 218/384 to 318/384. Under `book_v1` the old reading still holds and
    #: mixing stays off. Mixing defeats *prediction*, and under
    #: `subtractive_chebyshev_v1` no competent opponent has to predict us: the
    #: field we are required to publish has a unique peak on our own cell, so it
    #: can simply look. What it buys is not secrecy but a different road, and a
    #: pursuer that commits its barriers to one road pays for that.
    #:
    #: Where it WOULD have a mechanism is a lag-1 physics like `book_v1`, whose
    #: fix is one step stale and spread over about four cells - and there our
    #: thief already survives everything, so the gain is unmeasurable from above
    #: instead of from below. Addressable, off, and honestly labelled.
    mix_margin: float = 0.0
    #: Weight on how many escape routes survive our NEXT move, not this one.
    #: `w_strike` refuses a cell the pursuer can take; this refuses a cell whose
    #: every exit the pursuer can take the turn after. The distinction is the
    #: whole difference between being chased and being cut off, and it is the
    #: only way our thief loses in the lab: it survives every archetype in the
    #: pool and is taken by our own police, which does not chase it - it takes
    #: the ground away. `w_mobility` counts doors and cannot see this, because
    #: it counts a door the pursuer is standing behind.
    #:
    #: That day arrived. This was recorded as INERT - "survival against our own
    #: police is 0% at EVERY weight, and 100% against every other archetype" -
    #: and the reading was true of the pool that measured it and false of the
    #: term. Two blind spots were doing the work: the objective rebuilt our
    #: brain every seed (see `learn.arena.SERIES`) and our own police could not
    #: squeeze in time (see `gap_window`). With both fixed, this is the single
    #: strongest thief lever there is. Measured 2026-08-23, 48 seeds x 6 windows
    #: on fresh seeds:
    #:
    #:   registered_v3   0.0 -> 3.5   9.745 -> 9.827 pts, and najamjad's cage
    #:                                goes 194/288 -> **288/288**
    #:   subtractive     1.01 -> 3.5  with mix_margin 0.25, 9.840 -> 9.905
    #:   book_v1         unchanged - every candidate measured worse there
    #:
    #: Raising `w_strike` instead does nothing once this is set: 10.0 and 12.0
    #: are byte-identical to the shipped value over 1152 paired sub-games. The
    #: refusal this term expresses - do not take a cell whose every exit the
    #: pursuer can hold - is the one a squeezing police punishes, and the one
    #: `w_strike` (which refuses only the cell itself) cannot express.
    w_safe2: float = 0.0
    #: Weight on keeping away from a cell an earlier sub-game of THIS series
    #: died on, and how far that push reaches in BFS steps.
    #:
    #: The one term that is not about this sub-game at all. A match is six
    #: windows from the same two signed starting cells against the same
    #: opponent, and a deterministic evader plays the sixth exactly as it played
    #: the first. Audited from `result.my_steps` in the sealed logs: of 22
    #: archived series and 67 thief sub-games, 38 ended in capture, **eight
    #: series lost every thief window and six of those lost them at the
    #: identical step** - vibecode at step 14 on [6, 5] in three friendlies
    #: running, najamjad at 30, uoh-ay26 at 10 on [5, 5], orcai-mj at 16. Five
    #: of the six died on one repeated cell. Mixing does not answer it: it
    #: varies the road, and a funnel gathers every road.
    #:
    #: A weight rather than a constant because it is worth different amounts
    #: under different physics, which is the same reason every other weight here
    #: is one. Swept 2026-08-23 over the whole pool, 3312 sub-games per cell:
    #:
    #:   physics             off      (2,1)    (4,2)
    #:   registered_v3     9.535     9.700    9.766     <- 308 captures -> 155
    #:   subtractive       9.777     9.958    9.926     <- 148 captures ->  28
    #:   book_v1           9.888     9.903    9.893     <- 74 captures ->  64
    #:
    #: So the registered file carries (4, 2) and every book/subtractive file
    #: carries (2, 1). A LARGE weight is not free: under `book_v1` at (12, 3)
    #: the pool takes 43 sub-games where the term switched off takes 20 - the
    #: thief spends the board avoiding one cell and gets run down elsewhere. The
    #: first shipped version scaled this off `w_strike` (~8-9) and was tuned
    #: against a single foil; that is the value this sweep replaced.
    w_grave: float = 2.0
    grave_radius: int = 1


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
    # Searchable, but the archive is the authority on it and the lab's margin is
    # only about two standard errors - so treat a search that moves it far from
    # 1 the way `police_mix_margin` is treated, and check the conversion count
    # in `learn review` before writing the result to `config/`.
    "w_pounce": (0.0, 4.0, False),
    "w_cut": (0.0, 2.0, False),
    # Floors below zero for the same reason as `backtrack_penalty`: 0 is the
    # "off" value and every default must sit STRICTLY inside its box, so the
    # search can reach the off state from either side. Anything <= 0 runs the
    # incumbent selection untouched.
    "police_mix_margin": (-0.5, 2.0, False),
    "w_mobility": (0.0, 2.0, False),
    "w_mobility2": (0.0, 1.5, False),
    "w_territory": (0.0, 1.0, False),
    "trap_floor": (0, 24, True),
    # Floor below zero for the reason given above `police_mix_margin`: 0.0 is
    # this term's OFF value and a default must sit strictly inside its box, so
    # the search has to be able to reach off from either side. Anything <= 0
    # skips the seam scan entirely.
    "w_lifeboat": (-0.25, 1.0, False),
    "w_wall_side": (-0.25, 1.0, False),
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
    "mix_margin": (-0.5, 3.0, False),
    "w_safe2": (-0.5, 4.0, False),
    # Floor below zero for the reason given above `police_mix_margin`: 0.0 is
    # this term's OFF value and every default must sit strictly inside its box.
    "w_grave": (-1.0, 16.0, False),
    "grave_radius": (0, 4, True),
}

#: Which half of the vector each role reads. Spelled out rather than derived
#: from a name prefix: the prefix rule silently filed every new key under the
#: thief, so a `--role police` search would have left three police keys at their
#: defaults while reverting them in the thief's file.
POLICE_KEYS = ("peak_window", "gap_window", "kill_shot_ratio", "seal_ratio",
               "seal_distance", "endgame_reserve", "belief_floor", "police_fresh_min",
               "claim_threshold", "pounce_floor", "flee_bias", "w_pounce", "w_cut",
               "police_mix_margin")
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


def active(path: Path | None = None) -> Doctrine:
    """The doctrine this process plays: the tuned file if present, else v5.

    Announced at load, because "which policy am I actually running" is not
    something a league match should have to infer from how it played.

    The cache is keyed on the RESOLVED path, never on the argument. Caching
    ``active(None)`` looks equivalent and is not: every ordinary call passes no
    argument, so the key is `None` for all of them and the first load is handed
    back for the life of the process however `P2P_DOCTRINE` changes afterwards.
    Measured 2026-08-21 - a test that set the variable to the subtractive
    doctrine silently supplied it to every later caller, so a replay of the
    najamjad cage under the *default* physics ran the *counted* doctrine and
    reported a capture that the default doctrine does not suffer.
    """
    return _load_active_cached(path or default_path())


@lru_cache(maxsize=4)
def _load_active_cached(path: Path) -> Doctrine:
    if not path.exists():
        log.info("doctrine: shipped defaults (no %s)", path)
        return Doctrine()
    doctrine = loads(path.read_text(encoding="utf-8"))
    changed = sum(getattr(doctrine, k) != getattr(Doctrine(), k) for k in SPACE)
    log.info("doctrine: tuned from %s (%d of %d fields differ from the defaults)",
             path, changed, len(SPACE))
    return doctrine


#: `active` is a thin resolver in front of the cache, so the cache-clearing hook
#: has to be re-exposed on it: callers know `active` and should not have to know
#: which private function happens to hold the memo.
_load_active = _load_active_cached
active.cache_clear = _load_active_cached.cache_clear
active.cache_info = _load_active_cached.cache_info
