"""Every mixing margin we ship must be a decided number, and here is each decision.

`strategy.mixing.choose` returns the bare argmax whenever its margin is ``<= 0``,
so a negative or zero margin is not "a little mixing" - it is a policy that is a
pure function of the view. The module exists because that property lost us
sub-games: replayed from the same signed start cells, our thief produced six
byte-identical trajectories in six sub-games, and against uoh-ay26 it was taken
on (5,5) at step 10 in all three of the sub-games it played as thief, having
reached (5,5) in four moves every time.

A doctrine that omits the keys does not opt out of that - it rides on
``Doctrine()``, whose margins are 0.0, and plays deterministically while its
file says nothing at all. Three of the five shipped doctrines were in exactly
that state: `registered_v3`, `orcai-mj` and `amireman` named neither key, so
both of their roles were pure functions and no diff of those files could show
it. Every doctrine now declares both, and this file is the record of why.

**The lab can price mixing but cannot value it.** No member of the sparring pool
exploits repetition *across* sub-games (`replayer` replays its own archived path,
not an adaptation to us), so the arena only ever sees mixing's cost, and a search
duly drives the margin to zero or below. That is the same blind spot as `evader`
and `cager`, in a third place - which is why these are set by hand, and why the
rule is *the largest margin whose cost is inside the noise* rather than the
argmax of a number the objective cannot compute.

Measured 2026-08-22, each doctrine under its own physics, 60 seeds against the
28-member pool, every other key held fixed. The path counts are distinct
trajectories in six sub-games against a *fixed* foil (`najamjad-cage` for our
thief, `path:gal-roy1` for our police); a stochastic foil cannot measure this,
and neither can a bare argmax check, because `thief_brain` already adds
``rng.random() * 1e-3`` to every score and so breaks exact ties on its own.

One correction is recorded here rather than quietly dropped. `doctrine.json`'s
thief margin was originally switched off on a measurement against `constrictor`
- and twelve hours later the pool's own audit found that `constrictor` never
moved. It has since been removed from the pool entirely. The number below is
unchanged, but it now stands on the re-measurement, not on that one.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from p2p_pursuit.strategy.mixing import choose
from p2p_pursuit.strategy.params import active

BOOK = Path("config/doctrine.json")
SUBTRACTIVE = Path("config/doctrine-subtractive.json")
REGISTERED_V3 = Path("config/doctrine-registered_v3.json")
ORCAI = Path("config/doctrine-orcai-mj.json")
AMIREMAN = Path("config/doctrine-amireman.json")

#: (doctrine, key) -> (value, why). Every entry is a measured decision.
EXPECTED: dict[tuple[Path, str], tuple[float, str]] = {
    (BOOK, "mix_margin"): (
        -0.146074,
        "OFF, and deliberately. Under book the pursuer's fix arrives a step "
        "stale, and mixing on top of an already-noisy estimate costs more than "
        "it buys. Re-measured at n=60 after the archetype that justified it was "
        "found to be a statue: 9.877 pts with it off, 9.830 at 0.02, 9.717 at "
        "0.05 - monotone, with survival falling 97.5% -> 96.6% -> 94.3%. "
        "Mixing helps where the information is good and hurts where it is not, "
        "which is why the subtractive thief goes the other way.",
    ),
    (BOOK, "police_mix_margin"): (
        0.05,
        "18.940 pts against 18.762 at the 0.08 it replaces and 18.738 at 0.10; "
        "capture 92.9% vs 91.7%. All three already walk six distinct approach "
        "paths in six sub-games, so this buys points, not unpredictability.",
    ),
    (SUBTRACTIVE, "mix_margin"): (
        0.25,
        "Raised from 0.05 on 2026-08-23, and the reason the old measurement "
        "read the other way is that the POLICE changed underneath it. With "
        "`gap_window` fixed (8 -> 6) our own pursuer starts its squeeze in time, "
        "and against a pursuer that takes ground rather than distance, being "
        "unpredictable finally buys something: over 64 seeds x 6 windows, 9.895 "
        "pts against 9.826 at 0.05, and our thief's survivals against `mirror` "
        "go 218/384 -> 318/384 - 47 better, 6 worse, paired. Swept by hand at "
        "-0.15/0/0.05/0.10/0.25/0.50; 0.50 is worse again (9.856). PER PHYSICS "
        "and not a global lesson: the same sweep says `book_v1` wants mixing "
        "OFF, where 0.25 takes najamjad's cage from 288/288 to 125/288.",
    ),
    (SUBTRACTIVE, "police_mix_margin"): (
        0.05,
        "Kept rather than raised. 0.10 measures 18.905 against this 18.810, "
        "which is 0.095 pts - inside the noise at n=60 - and this is the "
        "doctrine that plays the counted matches. A sub-noise gain is not a "
        "reason to move the police half of a vector that is scoring 3/3 on the "
        "wire.",
    ),
    (REGISTERED_V3, "mix_margin"): (
        0.10,
        "Free: 9.736 pts against 9.717 with it off, and it takes our thief from "
        "four distinct paths in six sub-games to six. 0.20 gives back the gain "
        "(9.717) for no further diversity.",
    ),
    (REGISTERED_V3, "police_mix_margin"): (
        0.05,
        "19.214 pts against 19.143 off and 19.012 at 0.10, capture 94.8%. One "
        "distinct approach path in six sub-games becomes three.",
    ),
    (ORCAI, "mix_margin"): (
        0.10,
        "9.710 pts, identical to the same doctrine with mixing off, while two "
        "distinct paths in six sub-games become four. 0.20 measures 9.725 and "
        "buys no further diversity, so the smaller margin is taken - it cannot "
        "reach as far into the candidate list on a turn that matters.",
    ),
    (ORCAI, "police_mix_margin"): (
        0.02,
        "18.536 pts against 17.667 off - capture 90.2% vs 84.4% - and two "
        "distinct approach paths become six. Unusually small because 0.05 is "
        "measurably worse here at 18.202; this vector's distances sit closer "
        "together than the book default's.",
    ),
    (AMIREMAN, "mix_margin"): (
        0.10,
        "9.558 pts against 9.333 off, survival 91.2% vs 86.7%, and two distinct "
        "paths in six sub-games become six. The largest thief gain of the five "
        "doctrines, on the vector with the weakest evasion to begin with.",
    ),
    (AMIREMAN, "police_mix_margin"): (
        0.05,
        "17.869 pts against 16.643 off - capture 85.8% vs 77.6%, the largest "
        "police gain of the five. Recorded even though no contract currently "
        "points at this file, so that wiring it up later cannot silently ship a "
        "deterministic pair.",
    ),
}


@pytest.mark.parametrize(("path", "key"), sorted(EXPECTED, key=lambda k: (k[0].stem, k[1])),
                         ids=lambda v: v.stem if isinstance(v, Path) else v)
def test_the_margin_is_the_one_that_was_measured(path: Path, key: str):
    """A ratchet, not a preference: moving a margin must be a deliberate act."""
    wanted, why = EXPECTED[(path, key)]
    assert getattr(active(path), key) == pytest.approx(wanted), (
        f"{path.name}:{key} moved. It was set to {wanted} because: {why}"
    )


@pytest.mark.parametrize(("path", "key"), sorted(EXPECTED, key=lambda k: (k[0].stem, k[1])),
                         ids=lambda v: v.stem if isinstance(v, Path) else v)
def test_the_margin_is_recorded_in_the_file_not_inherited_from_a_default(path: Path, key: str):
    """A doctrine that omits the key rides on ``Doctrine()`` and reads as tuned.

    `doctrine-subtractive.json` omitted `police_mix_margin` entirely, so the file
    said nothing while the police played the 0.0 default - deterministic - and
    the omission was invisible in every diff of that file. Three more doctrines
    were later found in the same state, both keys missing from each.
    """
    assert key in json.loads(path.read_text(encoding="utf-8"))


def test_every_shipped_doctrine_declares_both_margins():
    """The invariant the three silent doctrines broke, stated over the directory.

    Enumerated from `config/` rather than from `EXPECTED`, so a doctrine added
    tomorrow fails here until somebody measures it and writes down why.
    """
    shipped = sorted(Path("config").glob("doctrine*.json"))
    assert shipped, "no doctrines found - is the test running from the repo root?"
    for path in shipped:
        raw = json.loads(path.read_text(encoding="utf-8"))
        missing = {"mix_margin", "police_mix_margin"} - set(raw)
        assert not missing, (
            f"{path.name} does not declare {sorted(missing)}, so it plays the 0.0 "
            f"default - a pure function of the view - while its file says nothing. "
            f"Measure it and add it to EXPECTED."
        )


def test_nine_of_the_ten_margins_actually_mix():
    """The blanket claim this file started as, kept where it is true.

    Stated as a count rather than per-key so it fails loudly if a future merge
    switches a role off, without asserting the one case measurement refused.
    """
    on = [(path.stem, key) for (path, key), _ in EXPECTED.items()
          if getattr(active(path), key) > 0.0]
    assert len(on) == 9, f"expected nine live margins, found {sorted(on)}"
    off = [(path.stem, key) for (path, key), _ in EXPECTED.items()
           if getattr(active(path), key) <= 0.0]
    assert off == [("doctrine", "mix_margin")], (
        f"the book thief is the only margin measurement refused; found {off}"
    )


def test_mixing_is_bounded_to_moves_that_are_nearly_best():
    """Why a small positive margin is free: it cannot reach a decisive move.

    The one step out of a closing strike zone is worth several points of
    `w_strike`, far more than any margin we ship, so it is still taken with
    probability 1 no matter which way the rng falls.
    """
    scores = {"N": 10.0, "S": 9.99, "E": 2.0, "W": 1.0, "STAY": 0.5}
    rng = random.Random(0)
    drawn = {choose(list(scores), scores.__getitem__, 0.05, rng, prefer=max)
             for _ in range(200)}
    assert drawn == {"N", "S"}, "the margin reached a move it should not have"

    decisive = {"N": 10.0, "S": 2.0, "E": 2.0, "W": 1.0, "STAY": 0.5}
    assert {choose(list(decisive), decisive.__getitem__, 0.05, rng, prefer=max)
            for _ in range(200)} == {"N"}


def test_the_largest_shipped_margin_still_cannot_reach_a_decisive_move():
    """0.10 is the biggest margin above, and `w_strike` is ~8-9 points away."""
    decisive = {"N": 10.0, "S": 2.0, "E": 2.0, "W": 1.0, "STAY": 0.5}
    rng = random.Random(1)
    largest = max(value for value, _ in EXPECTED.values())
    assert {choose(list(decisive), decisive.__getitem__, largest, rng, prefer=max)
            for _ in range(200)} == {"N"}
