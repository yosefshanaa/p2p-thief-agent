"""The one step of guessing left, once the fix has removed all the others.

A fix is evidence about the past, and the opponent moves again before we see
anything new. `strategy.predict` fills that gap with one line of behaviour - an
evader prefers cells further from its pursuer, a pursuer prefers cells nearer -
and leaves the strength of the preference to the offline search.
"""

from __future__ import annotations

from p2p_pursuit.domain.board import Board
from p2p_pursuit.strategy.predict import spread, strike_zone

SIZE = 7


def test_no_lag_is_a_delta_on_the_fix():
    """Under a model that serves after emitting there is nothing to predict."""
    assert spread(Board(SIZE), (3, 3), (0, 0), steps=0, bias=2.0) == {(3, 3): 1.0}


def test_it_is_a_distribution():
    where = spread(Board(SIZE), (3, 3), (0, 0), steps=1, bias=1.8)
    assert abs(sum(where.values()) - 1.0) < 1e-9
    assert set(where) == {(3, 3), (2, 3), (4, 3), (3, 2), (3, 4)}


def test_a_bias_of_one_is_the_honest_uniform_prior():
    where = spread(Board(SIZE), (3, 3), (0, 0), steps=1, bias=1.0)
    assert len({round(v, 9) for v in where.values()}) == 1


def test_an_evader_is_expected_to_open_the_gap():
    """Anchor at the top-left, so south and east are away from it."""
    where = spread(Board(SIZE), (3, 3), (0, 0), steps=1, bias=2.0)
    assert where[(4, 3)] > where[(3, 3)] > where[(2, 3)]
    assert where[(3, 4)] > where[(3, 2)]


def test_a_pursuer_is_expected_to_close_it():
    where = spread(Board(SIZE), (3, 3), (0, 0), steps=1, bias=0.5)
    assert where[(2, 3)] > where[(3, 3)] > where[(4, 3)]


def test_it_never_puts_mass_through_a_barrier():
    board = Board(SIZE, {(2, 3), (4, 3), (3, 2)})
    where = spread(board, (3, 3), (0, 0), steps=2, bias=1.8)
    assert not (set(where) & board.barriers)


def test_the_strike_zone_is_every_cell_it_could_step_to():
    board = Board(SIZE)
    zone = strike_zone(board, {(3, 3): 1.0})
    assert zone == dict.fromkeys([(3, 3), *board.open_neighbors((3, 3))], 1.0)


def test_converging_approaches_add_rather_than_tie():
    """Two ways to reach one cell make it more dangerous, not equally so."""
    zone = strike_zone(Board(SIZE), {(3, 3): 0.5, (3, 5): 0.5})
    assert zone[(3, 4)] == 1.0
    assert zone[(3, 3)] == 0.5
