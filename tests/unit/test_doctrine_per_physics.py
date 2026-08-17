"""A doctrine belongs to a scent physics, and the repo must keep them paired.

Playing the wrong pairing is silent - nothing errors, the agent just plays a
worse game - so the pairing is asserted here rather than left to whoever writes
the next contract file.

Measured 2026-08-17 on hold-out seeds 9000-9011 against the full sparring pool,
in league points per sub-game:

                              book_v1    subtractive
    doctrine.json              13.19        14.11
    doctrine-subtractive.json  12.82        14.94

Each wins under its own physics, and the best cell is the kit's physics with
the doctrine searched under it.

Re-searched under v8 (both roles, 28 keys, hold-out gated): the subtractive
vector went **14.313 -> 15.113** points, with thief survival **66.2% -> 99.1%**
and capture already at 100%. All 28 keys differ from the book vector, which is
what "a doctrine belongs to a physics" means in practice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2p_pursuit.domain.scent import BOOK_V1, MODELS, SUBTRACTIVE_V1
from p2p_pursuit.strategy import params

REPO = Path(__file__).resolve().parents[2]
PAIRS = {BOOK_V1: REPO / "config" / "doctrine.json",
         SUBTRACTIVE_V1: REPO / "config" / "doctrine-subtractive.json"}


@pytest.mark.parametrize("model,path", sorted(PAIRS.items()))
def test_every_paired_doctrine_exists_and_loads(model: str, path: Path) -> None:
    assert model in MODELS
    assert path.exists(), f"{model} has no doctrine at {path}"
    doctrine = params.active(path)
    # A subset is fine and normal - keys outside the search space fall back to
    # the dataclass defaults - but a key the dataclass does not know is a typo
    # that would be silently ignored at load and never applied to a match.
    assert set(json.loads(path.read_text())) <= set(vars(doctrine))


def test_the_two_doctrines_are_actually_different_vectors() -> None:
    """If a copy ever ships unsearched, the pairing is decoration. The search
    moved 15 of 23 keys, so a handful differing is not enough to prove it ran.

    Compared as *loaded* doctrines rather than as raw JSON: a file may legally
    omit keys, which fall back to the dataclass defaults, and comparing the raw
    dicts key-by-key raises rather than answering the question the moment one
    file is regenerated ahead of the other.
    """
    book, sub = params.active(PAIRS[BOOK_V1]), params.active(PAIRS[SUBTRACTIVE_V1])
    differing = [k for k in params.SPACE if getattr(book, k) != getattr(sub, k)]
    assert len(differing) >= 10, f"only {differing} differ - was the search actually run?"


def test_the_thief_half_moved_where_the_physics_hurt_it() -> None:
    """Under subtractive decay the thief is in more danger, and pays for caution.

    v7 asserted this as `stay_penalty` and `corner_penalty` both rising, on the
    reasoning that a subtractive field leaks the thief's trail more brightly.
    Half of that survived the v8 re-search and half inverted, for a reason worth
    recording: the leak is now **total under both models** - the field is
    invertible either way - and the only difference is the *lag*. Subtractive
    serves after emitting, so its fix is the pursuer's cell *now* rather than one
    step ago, and exact machinery displaces the diffuse kind.

    So corner discipline goes **up** (0.244 -> 0.409) and the strike term goes
    **up** (8.13 -> 9.14), while `stay_penalty`, `w_territory` and `w_trap` fall
    to zero - hedges against uncertainty that no longer exists.
    """
    book, sub = params.active(PAIRS[BOOK_V1]), params.active(PAIRS[SUBTRACTIVE_V1])
    assert sub.corner_penalty > book.corner_penalty, "the edge stays more expensive"
    assert sub.w_strike > book.w_strike, "and a lag-0 fix makes the strike map sharper"
    assert sub.stay_penalty <= book.stay_penalty, (
        "the blanket hold penalty is a proxy for uncertainty, and there is less "
        "of it here - if this ever rises again, the reasoning above is wrong")


def test_a_contract_selects_both_together_or_neither() -> None:
    """P2P_SCENT_MODEL and P2P_DOCTRINE are one decision in two variables. Any
    committed contract naming the kit's physics must name its doctrine too."""
    for env_file in sorted((REPO / "config" / "opponents").glob("*.env")):
        text = env_file.read_text(encoding="utf-8")
        live = [ln.strip() for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
        if any(ln == f"P2P_SCENT_MODEL={SUBTRACTIVE_V1}" for ln in live):
            assert any(ln.startswith("P2P_DOCTRINE=") and "subtractive" in ln for ln in live), (
                f"{env_file.name} plays the kit's physics on the wrong doctrine")
