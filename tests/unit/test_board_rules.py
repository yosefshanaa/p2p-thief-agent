"""Stage-1 physics: movement legality, barriers, enclosure, scoring."""

import pytest

from p2p_pursuit.domain.board import Board, target_of
from p2p_pursuit.domain.rules import (
    POLICE,
    THIEF,
    Decision,
    apply_decision,
    safe_decision,
    validate,
)
from p2p_pursuit.domain.scoring import CAPTURE, SURVIVAL, TECHNICAL_LOSS, ScoreTable


def test_orthogonal_targets():
    assert target_of((3, 3), "N") == (2, 3)
    assert target_of((3, 3), "S") == (4, 3)
    assert target_of((3, 3), "E") == (3, 4)
    assert target_of((3, 3), "W") == (3, 2)
    assert target_of((3, 3), "STAY") == (3, 3)


def test_legal_moves_at_corner_and_barrier():
    b = Board(7)
    assert set(b.legal_moves((0, 0))) == {"S", "E", "STAY"}
    b.add_barrier((0, 1))
    assert set(b.legal_moves((0, 0))) == {"S", "STAY"}


def test_diagonals_do_not_exist():
    assert validate(Board(7), THIEF, (3, 3), Decision(move="NE"), 0, 14) is not None


def test_move_off_board_and_into_barrier_rejected():
    b = Board(7)
    b.add_barrier((3, 4))
    assert validate(b, THIEF, (0, 0), Decision(move="N"), 0, 14) is not None
    assert validate(b, THIEF, (3, 3), Decision(move="E"), 0, 14) is not None


def test_barrier_rules():
    b = Board(7)
    ok = Decision(move="STAY", barrier=(3, 4))
    assert validate(b, POLICE, (3, 3), ok, 0, 14) is None
    assert validate(b, POLICE, (3, 3), Decision(move="STAY", barrier=(3, 3)), 0, 14) is None
    assert validate(b, THIEF, (3, 3), ok, 0, 14) is not None          # thief may not
    assert validate(b, POLICE, (3, 3), Decision(move="N", barrier=(3, 4)), 0, 14) is not None
    assert validate(b, POLICE, (3, 3), ok, 14, 14) is not None        # quota exhausted
    assert validate(b, POLICE, (3, 3), Decision(move="STAY", barrier=(5, 5)), 0, 14) is not None
    b.add_barrier((3, 4))
    assert validate(b, POLICE, (3, 3), ok, 0, 14) is not None         # already barred


def test_apply_and_enclosure():
    b = Board(7)
    assert apply_decision(b, (3, 3), Decision(move="E")) == (3, 4)
    assert apply_decision(b, (3, 3), Decision(move="STAY", barrier=(3, 4))) == (3, 3)
    assert (3, 4) in b.barriers
    b2 = Board(7, {(0, 1), (1, 0)})
    assert b2.is_enclosed((0, 0))
    assert not b2.is_enclosed((5, 5))


def test_safe_decision_falls_back_to_legal():
    b = Board(7)
    fixed = safe_decision(b, THIEF, (0, 0), 0, 14, Decision(move="N"))
    assert validate(b, THIEF, (0, 0), fixed, 0, 14) is None


def test_score_table():
    t = ScoreTable.from_config({"capture_cop": 20, "capture_thief": 5, "survival_cop": 5,
                                "survival_thief": 10, "tie_score": 2, "technical_loss": 0})
    assert t.score(CAPTURE) == (20, 5)
    assert t.score(SURVIVAL) == (5, 10)
    assert t.score(TECHNICAL_LOSS) == (0, 0)
    with pytest.raises(ValueError):
        t.score("draw")
