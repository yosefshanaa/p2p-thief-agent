"""Every mixing margin we ship must be a decided number, and here is each decision.

`strategy.mixing.choose` returns the bare argmax whenever its margin is ``<= 0``,
so a negative or zero margin is not "a little mixing" - it is a policy that is a
pure function of the view. The module exists because that property lost us
sub-games: replayed from the same signed start cells, our thief produced six
byte-identical trajectories in six sub-games, and against uoh-ay26 it was taken
on (5,5) at step 10 in all three of the sub-games it played as thief, having
reached (5,5) in four moves every time.

Three of the four margins were nevertheless off, silently, in both doctrines:

    doctrine.json              mix_margin -0.146   police_mix_margin  0.152
    doctrine-subtractive.json  mix_margin -0.349   police_mix_margin  0.0  (absent)

Not a bug in the search - a hole in its objective. No member of the sparring
pool exploits repetition *across* sub-games (`replayer` replays its own archived
path, not an adaptation to us), so the arena can only ever see mixing's cost and
never its benefit, and a search duly drives the margin to zero or below. That is
the same blind spot as `evader` and `cager`, in a third place.

So the ratchet cannot be "mixing is always on" - measurement refuses that in one
of the four cases. It is "every margin is a number somebody decided, and moving
it fails this test". Each was a single-key sweep against the pool with every
other key held fixed; the numbers are in `EXPECTED` below.
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

#: (doctrine, key) -> (value, why). Every entry is a measured decision.
EXPECTED: dict[tuple[Path, str], tuple[float, str]] = {
    (SUBTRACTIVE, "mix_margin"): (
        0.05,
        "free: 95.6% pool survival and 100% against our own police at n=120, "
        "identical to the -0.349 it replaced. Mixing is bounded to moves within "
        "the margin of the best, so a decisive step is still taken with "
        "probability 1 - it spends nothing on the turns that decide a sub-game.",
    ),
    (SUBTRACTIVE, "police_mix_margin"): (
        0.05,
        "evader 17.5% -> 21.7% at n=120, with holder, camper and "
        "recorded:orcai-mj unmoved at 100%.",
    ),
    (BOOK, "police_mix_margin"): (
        0.08,
        "dominates the 0.152 it replaced on every opponent at n=60: evader "
        "13.3%->21.7%, holder 73.3%->90.0%, clone:amireman-v2 83.3%->98.3%, "
        "recorded:orcai-mj unchanged at 100%.",
    ),
    (BOOK, "mix_margin"): (
        -0.146074,
        "OFF, and deliberately. Under book the pursuer's fix arrives a step "
        "stale, and mixing on top of an already-noisy estimate costs more than "
        "it buys: at n=120 turning it on takes survival against `constrictor` "
        "from 75.8% to 50.0% for a 6-point gain against our own police. The "
        "cage archetype is the one that models the teams who beat us, so that "
        "column is the expensive one. Mixing helps where the information is "
        "good and hurts where it is not - which is why the subtractive thief "
        "above goes the other way.",
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
    the omission was invisible in every diff of that file.
    """
    assert key in json.loads(path.read_text(encoding="utf-8"))


def test_three_of_the_four_margins_actually_mix():
    """The blanket claim this file started as, kept where it is true.

    Stated as a count rather than per-key so it fails loudly if a future merge
    switches a second role off, without asserting the one case measurement
    refused.
    """
    on = [key for (path, key), _ in EXPECTED.items() if getattr(active(path), key) > 0.0]
    assert len(on) == 3, f"expected three live margins, found {sorted(on)}"


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
