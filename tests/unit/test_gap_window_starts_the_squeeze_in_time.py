"""`gap_window` decides whether the squeeze ever starts, and every file had it wrong.

`PoliceBrain._evading` is the gate on the whole squeeze:

    return len(self._gaps) == self._gaps.maxlen and gap >= self._gaps[0]

`maxlen` is `gap_window`, so the number is doing two jobs at once - how many
turns of pursuit must be on record before the test may fire at all, and how old
the gap it compares against is. Shipped at 8, which is the top of its own
`SPACE` box, the police needed eight turns of history and then asked whether it
had closed any ground in eight turns. Against an evader it had not, but by then
the barriers that would have answered were half spent and the thief was already
on ground it could hold.

Found by ablating a CEM result one key-group at a time: of the seven groups the
search moved, six were byte-identical no-ops over 368 paired sub-games and this
was the whole gain. `peak_window`, its neighbour in the vector, is inert -
identical scores at 4, 7, 10 and 14.

The values below are measured, not preferred, and they differ per physics
because the curve has a real interior optimum: too large and the squeeze never
starts, too small and it fires on two turns of noise and spends barriers where
a plain chase would have converted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2p_pursuit.strategy.params import SPACE, active

#: file -> (gap_window, what it was measured against)
EXPECTED: dict[str, tuple[int, str]] = {
    "config/doctrine.json": (
        3,
        "book_v1, already correct when the sweep found the others. 19.158 "
        "pts/sub-game against 18.662 at 8, and `evader` converts 187/240 here "
        "against 10/240 at 5 - this physics wants the earliest trigger of the "
        "three.",
    ),
    "config/doctrine-subtractive.json": (
        6,
        "8 -> 6: 18.315 -> 19.215 pts/sub-game over 3312 sub-games on fresh "
        "seeds. `recorded:vibecode` - the team that took our police 0/3 in "
        "three friendlies running - goes 25/240 to 240/240, and conversion "
        "against `evader` goes 0.15 to 0.35. This is the file the counted "
        "matches play.",
    ),
    "config/doctrine-registered_v3.json": (
        5,
        "7 -> 5: 19.342 -> 19.527, the mean of two independent 40-seed runs. 6 "
        "measures within noise of 5 (19.499); 5 won two of the three runs.",
    ),
    "config/doctrine-orcai-mj.json": (
        3,
        "7 -> 3: 18.555 -> 19.176 over 24 seeds, paired 56 worse for 7. Book "
        "physics, like `doctrine.json`, and it lands on the same value.",
    ),
    "config/doctrine-amireman.json": (
        6,
        "LEFT ALONE. 3 measures 17.763 against this 17.749 - paired 28 better, "
        "29 worse, which is a tie - and no contract points at this file. A "
        "sub-noise difference is not a reason to move a shipped number.",
    ),
}


@pytest.mark.parametrize(("path", "wanted"), sorted((p, v[0]) for p, v in EXPECTED.items()))
def test_the_gap_window_is_the_one_that_was_measured(path: str, wanted: int):
    """A ratchet: moving this must be a deliberate, re-measured act."""
    got = active(Path(path)).gap_window
    assert got == wanted, (
        f"{path}:gap_window is {got}, was set to {wanted} because: "
        f"{EXPECTED[path][1]}"
    )


def test_no_shipped_gap_window_sits_on_its_search_bound():
    """The bug this file exists for, stated as an invariant.

    Every one of these was at a bound - 8 is the top of the box - and a value at
    a bound means the search wanted to go further and could not, or that the
    objective could not see the term at all. Neither is a value to ship.
    """
    low, high, _ = SPACE["gap_window"]
    for path in EXPECTED:
        got = active(Path(path)).gap_window
        assert low < got < high, (
            f"{path}:gap_window is {got}, which sits on the search box "
            f"({low}, {high}) - re-measure it rather than shipping a bound"
        )


def test_the_evasion_gate_really_is_this_window():
    """Pins the coupling the docstring rests on, so a refactor cannot hide it."""
    from p2p_pursuit.strategy.police_brain import PoliceBrain

    doctrine = active(Path("config/doctrine-subtractive.json"))
    brain = PoliceBrain(doctrine)
    assert brain._gaps.maxlen == doctrine.gap_window, (
        "`_evading` no longer reads gap_window as its window length - every "
        "measurement in this file was taken through that coupling"
    )
