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


def test_neither_doctrine_lets_the_search_zero_out_corner_discipline() -> None:
    """Both physics punish the edge. Which punishes it *more* is no longer pinned.

    This test asserted `sub.corner_penalty > book.corner_penalty` for three
    searches, on the reasoning that subtractive leaks the thief's exact cell
    while book_v1's argmax was right 1 time in 9 - so the edge was more
    expensive under subtractive, where the pursuer knows where you are.

    That reasoning has been removed by its own fix. `tracking.unique_peak` now
    recovers the emitter under book_v1 as exactly as under subtractive (12/12
    against a native field, where it used to be 10/12 and 0/12 against a kernel
    snapshot), so the two models no longer differ in whether the position is
    known - only in the one-step lag. The asymmetry the ordering rested on is
    gone, and the next search duly put book's corner discipline ABOVE
    subtractive's (0.631 against 0.304). Two earlier assertions in this test
    flipped the same way and were retired for the same reason: an ordering
    without a live mechanism behind it is noise, and pinning it only guarantees
    a test edit after every re-tune.

    What is worth pinning is the thing that actually broke once. With no pool
    member able to punish a corner, a thief search drove `corner_penalty` to
    0.001 - and 54 of 54 of our archived thief deaths are on the outer two
    rings. So: both doctrines must still carry real corner discipline, whichever
    of them carries more.
    """
    for model, path in sorted(PAIRS.items()):
        doctrine = params.active(path)
        assert doctrine.corner_penalty > 0.05, (
            f"{model} has effectively no corner discipline "
            f"({doctrine.corner_penalty}) - has the pool stopped punishing the edge?")


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
