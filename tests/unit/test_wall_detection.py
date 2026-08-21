"""Seeing a wall while it is still a wall and not yet a cage.

najamjad's police walled column 3 one cell every other turn. Three of them were
down by their turn 7 and the escape it threatens expires on turn 9, so a thief
that only notices pockets notices too late - `_lifeboat` does not become
non-flat until step 11. These tests pin the earlier signal.
"""

from __future__ import annotations

from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.brains_base import BrainView
from p2p_pursuit.domain.rules import THIEF
from p2p_pursuit.strategy.params import active
from p2p_pursuit.strategy.thief_brain import ThiefBrain


def _view(barriers, own, opp_fix, size=7):
    return BrainView(
        role=THIEF, sub_game=1, step=8, own_pos=own, board=Board(size, set(barriers)),
        belief=None, opp_scent=None, own_scent=None, barriers_used=0, barrier_quota=14,
        steps_remaining=27, survival_threshold=35, trust=1.0, map_area=size * size,
        rng=None, opp_cells=(), opp_fix=opp_fix, opp_fix_lag=0, opp_lead=None)


def _brain():
    return ThiefBrain(active())


def test_an_open_board_declares_no_wall() -> None:
    assert _brain()._wall_line(_view([], (3, 3), (0, 0))) is None


def test_two_collinear_barriers_are_not_yet_a_wall() -> None:
    assert _brain()._wall_line(_view([(0, 3), (1, 3)], (3, 3), (0, 0))) is None


def test_three_collinear_barriers_project_the_whole_column() -> None:
    """Their turn 7 state - two turns before the escape expires."""
    line = _brain()._wall_line(_view([(0, 3), (1, 3), (2, 3)], (4, 5), (2, 2)))
    assert line == {(r, 3) for r in range(7)}


def test_the_term_is_silent_with_no_wall_and_no_pursuer() -> None:
    brain = _brain()
    assert brain._wall_side(_view([], (3, 3), (0, 0)), (3, 3)) == 0
    assert brain._wall_side(_view([(0, 3), (1, 3), (2, 3)], (4, 5), None), (4, 5)) == 0


def test_it_points_across_the_wall_not_away_from_it() -> None:
    """The gradient that matters: from (4,5), west must beat east. A builder
    walls away from itself and then crosses to finish the trap, so the side that
    looks safe is the side it is coming to."""
    brain = _brain()
    view = _view([(0, 3), (1, 3), (2, 3)], (4, 5), (2, 2))
    west, east = brain._wall_side(view, (4, 4)), brain._wall_side(view, (4, 6))
    assert west > east, f"west {west} must beat east {east}"


def test_the_gap_itself_scores_highest() -> None:
    """Standing in the gap IS the crossing. An earlier version returned 0 here
    because the cell belongs to the projected wall, which built a gradient that
    walked the thief to the door and then forbade the step through it."""
    brain = _brain()
    view = _view([(0, 3), (1, 3), (2, 3), (3, 3)], (5, 4), (4, 2))
    gap = brain._wall_side(view, (5, 3))
    away = brain._wall_side(view, (5, 5))
    assert gap > away, f"the gap scored {gap}, stepping away scored {away}"


def test_it_is_off_in_every_shipped_doctrine() -> None:
    """It has never beaten the cage in the lab, and the only cage we can test
    against does not react - so it ships searchable but disabled."""
    assert active().w_wall_side == 0.0
