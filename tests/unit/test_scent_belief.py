"""Scent golden values (book figure 4 + the 0.81 example) and belief mechanics."""

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.scent import EMISSION_KERNEL, ScentField, scent_model_document


def test_emission_matches_book_figure():
    f = ScentField(7)
    f.emit((3, 3))
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            assert f.grid[3 + dr][3 + dc] == EMISSION_KERNEL[dr + 2][dc + 2]


def test_book_numeric_example_09_to_081():
    f = ScentField(7)
    f.emit((3, 3))
    f.decay()
    assert f.grid[3][3] == 0.81


def test_clamp_at_focal_cap_and_edge_clipping():
    f = ScentField(7)
    f.emit((0, 0))          # kernel clipped at the corner, no crash
    f.emit((0, 0))
    assert f.grid[0][0] == 0.9   # clamped, never above the cap
    assert all(v <= 0.9 for row in f.grid for v in row)


def test_decay_snaps_dust_to_zero():
    f = ScentField(7)
    f.grid[0][0] = 0.001
    f.decay()  # 0.0009 < the 1e-3 cutoff -> silence, not eternal dust
    assert f.grid[0][0] == 0.0


def test_scent_model_document_is_lockable():
    doc = scent_model_document()
    assert doc["numeric_example"] == {"tau_0": 0.9, "after_one_decay": 0.81}
    assert doc["rho"] == 0.10


def test_belief_delta_diffuse_and_barriers():
    board = Board(7)
    b = BeliefMap.at(7, (3, 3))
    b.diffuse(board)
    assert abs(sum(map(sum, b.grid)) - 1.0) < 1e-9
    assert b.grid[3][3] > 0 and b.grid[2][3] > 0
    assert b.grid[0][0] == 0.0
    board.add_barrier((2, 3))
    b2 = BeliefMap.at(7, (3, 3))
    b2.diffuse(board)
    assert b2.grid[2][3] == 0.0  # no mass flows into a barrier


def test_scent_update_concentrates_on_fresh_trail():
    board = Board(7)
    opp = ScentField(7)
    opp.emit((5, 5))
    opp.decay()  # fresh trail at (5,5) = 0.81
    b = BeliefMap(7)
    b.scent_update(opp.snapshot(), board)
    assert b.argmax() == (5, 5)


def test_exclude_and_reset_on_dead_belief():
    board = Board(7)
    b = BeliefMap.at(7, (3, 3))
    b.exclude((3, 3), board)  # the only mass removed -> uniform reset
    assert abs(sum(map(sum, b.grid)) - 1.0) < 1e-9


def test_hint_update_shifts_mass():
    from p2p_pursuit.domain.hints import region_cells

    board = Board(7)
    b = BeliefMap(7)
    region = region_cells("north", 7)
    before = b.mass_in(region)
    b.hint_update(region, trust=1.0, board=board)
    assert b.mass_in(region) > before
