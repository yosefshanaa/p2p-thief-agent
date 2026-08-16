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
    moved 15 of 23 keys, so a handful differing is not enough to prove it ran."""
    book = json.loads(PAIRS[BOOK_V1].read_text())
    sub = json.loads(PAIRS[SUBTRACTIVE_V1].read_text())
    differing = [k for k in book if book[k] != sub[k]]
    assert len(differing) >= 10, f"only {differing} differ - was the search actually run?"


def test_the_thief_half_moved_where_the_physics_hurt_it() -> None:
    """Under subtractive decay the thief leaks more - its baseline survival was
    75% against 89% at home - so the search should have paid for caution."""
    book = json.loads(PAIRS[BOOK_V1].read_text())
    sub = json.loads(PAIRS[SUBTRACTIVE_V1].read_text())
    assert sub["stay_penalty"] > book["stay_penalty"]
    assert sub["corner_penalty"] > book["corner_penalty"]


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
