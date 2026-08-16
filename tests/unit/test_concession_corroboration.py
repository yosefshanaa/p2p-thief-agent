"""Reading an opponent's unsealed `caught: true` for what it actually is.

League kit SPEC 3.1: rule 46 (a barrier on the thief's own cell) and rule 47
(no legal move left) are facts only the thief can see, so it must announce them
- and only the thief profits from announcing one that is not true. The cop is
asked to corroborate against its **own** barrier record.

We record the verdict rather than impose a sanction, so these tests assert the
settlement is unchanged and the *evidence* is what moves.
"""

from __future__ import annotations

from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.domain.scoring import CAPTURE
from p2p_pursuit.peer import unsealed_events


class _Engine:
    """Only what `note_capture_confirmed` touches."""

    def __init__(self, role: str = POLICE, barriers: set | None = None,
                 last_claim_cell: tuple | None = None) -> None:
        self.role = role
        self.board = Board(7, set(barriers or ()))
        self.last_claim_cell = last_claim_cell
        self.finished: tuple | None = None

    def _finish(self, ending: str, winner: str, cause: str) -> None:
        self.finished = (ending, winner, cause)


def _cause(engine: _Engine, cell: list[int]) -> str:
    unsealed_events.note_capture_confirmed(engine, cell)
    assert engine.finished is not None
    ending, winner, cause = engine.finished
    assert (ending, winner) == (CAPTURE, POLICE), "settlement must not change"
    return cause


def test_an_answer_to_our_own_claim_is_not_second_guessed() -> None:
    """Its cell is checked against their revealed trail at the audit instead."""
    engine = _Engine(last_claim_cell=(4, 4))
    cause = _cause(engine, [4, 4])
    assert "concession" not in cause
    assert "unsealed answer" in cause


def test_a_barrier_on_the_conceded_cell_corroborates_rule_46() -> None:
    engine = _Engine(barriers={(2, 2)}, last_claim_cell=(5, 5))
    assert "corroborated: our barrier is on that cell" in _cause(engine, [2, 2])


def test_our_own_barriers_enclosing_the_cell_corroborate_rule_47() -> None:
    """A corner needs only two barriers - which is why the squeeze aims there."""
    engine = _Engine(barriers={(0, 1), (1, 0)}, last_claim_cell=(5, 5))
    assert "corroborated: our barriers enclose that cell" in _cause(engine, [0, 0])


def test_an_unexplained_concession_is_recorded_as_not_corroborated() -> None:
    """The point of the whole exercise: a false concession is worth +5 to them
    and +20 to us, so nobody in the exchange is motivated to catch it."""
    engine = _Engine(barriers={(6, 6)}, last_claim_cell=(5, 5))
    cause = _cause(engine, [3, 3])
    assert "NOT corroborated" in cause
    assert engine.finished[:2] == (CAPTURE, POLICE), "still settled, only flagged"


def test_the_thief_side_records_nothing_extra() -> None:
    """Barriers are the cop's instrument; a thief has no record to check."""
    engine = _Engine(role=THIEF)
    assert "concession" not in _cause(engine, [3, 3])


def test_a_claim_we_never_made_still_settles() -> None:
    """No remembered claim - e.g. the opponent's cop conceded to us - must not
    raise, because a crash here loses a sub-game that was played cleanly."""
    engine = _Engine(last_claim_cell=None)
    assert "unsealed answer" in _cause(engine, [1, 1])


def test_the_remembered_claim_does_not_survive_a_sub_game() -> None:
    """A claim from sub-game 1 would make a sub-game 3 concession at the same
    cell read as an answer, silently skipping the corroboration."""
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    engine = TurnEngine(POLICE, make_shared(), make_peer(POLICE), seed=5)
    engine.last_claim_cell = (4, 4)
    engine.start_sub_game(2)
    assert engine.last_claim_cell is None
