"""The scent-channel note judges turn 2, not turn 1.

A lagged trail is legitimately empty on the opening move: gal-roy1 send theirs
lag-1, so their turn 1 carries `{}` by design. Sampling turn 1 announced "NO
smell_grid" against a peer that does send one - evidence pointing the wrong way,
which is worse than no check at all. Measured live 2026-08-17.
"""

from __future__ import annotations

import logging

from p2p_pursuit.infra.interop_bridge import ReferenceBridge


class Bridge(ReferenceBridge):
    """Only the note is under test, so nothing else is constructed."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips the real __init__
        self._scent_note_for = None


def _notes(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "smell_grid" in r.getMessage()]


def test_turn_1_is_never_judged(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="p2p_pursuit.infra.interop_bridge"):
        Bridge()._note_scent_channel({"step": 1, "smell_grid": {}}, 1)
    assert _notes(caplog) == []


def test_turn_2_with_a_trail_reports_it_present(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="p2p_pursuit.infra.interop_bridge"):
        Bridge()._note_scent_channel({"step": 2, "smell_grid": {"3,3": 0.9, "3,4": 0.62}}, 1)
    assert "carries a smell_grid (2 cells)" in _notes(caplog)[0]


def test_turn_2_with_no_trail_is_the_finding_that_matters(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="p2p_pursuit.infra.interop_bridge"):
        Bridge()._note_scent_channel({"step": 2, "hint": "north"}, 1)
    assert "carries NO smell_grid" in _notes(caplog)[0]


def test_it_speaks_once_per_sub_game(caplog) -> None:
    bridge = Bridge()
    with caplog.at_level(logging.INFO, logger="p2p_pursuit.infra.interop_bridge"):
        bridge._note_scent_channel({"step": 2, "smell_grid": {"1,1": 0.9}}, 1)
        bridge._note_scent_channel({"step": 3, "smell_grid": {"1,1": 0.9}}, 1)
        bridge._note_scent_channel({"step": 2, "smell_grid": {"1,1": 0.9}}, 2)
    assert len(_notes(caplog)) == 2  # one for sub-game 1, one for sub-game 2


def test_a_sub_game_ending_before_turn_2_says_nothing_rather_than_lying(caplog) -> None:
    """A capture on turn 1 leaves the channel genuinely unmeasured."""
    with caplog.at_level(logging.INFO, logger="p2p_pursuit.infra.interop_bridge"):
        Bridge()._note_scent_channel({"step": 1, "smell_grid": {"1,1": 0.9}}, 4)
    assert _notes(caplog) == []


def test_a_missing_or_junk_step_is_not_treated_as_turn_2(caplog) -> None:
    bridge = Bridge()
    with caplog.at_level(logging.INFO, logger="p2p_pursuit.infra.interop_bridge"):
        bridge._note_scent_channel({"smell_grid": {}}, 1)
        bridge._note_scent_channel({"step": "n/a", "smell_grid": {}}, 1)
    assert _notes(caplog) == []
