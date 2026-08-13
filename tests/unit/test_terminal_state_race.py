"""A sub-game that ends mid-turn must not take the whole peer down.

Measured live vs orcai-mj on 2026-08-13. `_send_package` calls `link.reveal`,
which is a network round-trip; an inbound push declared a technical loss while
it was in flight; the `sent_reveal()` that followed hit a terminal machine and
raised out of the series thread:

    IllegalTransitionError: Illegal transition: TECHNICAL_LOSS -> VERIFYING

The peer died, our endpoint began returning 502, and the opponent - which was
retrying correctly - could never reconnect. In a counted match that is an
unrecoverable technical loss caused entirely by our own crash.

The phase machine stays strict (rules #4-5): these tests pin that ending the
sub-game first is treated as a race, while illegal *play* still raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2p_pursuit.peer.runtime import PeerRuntime
from p2p_pursuit.peer.state_machine import (
    COMMITTING,
    GamePhaseMachine,
    IllegalTransitionError,
)

BASE = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def engine(tmp_path):
    rt = PeerRuntime("thief", BASE / "config" / "thief", out_dir=tmp_path, num_games=6)
    eng = rt.engine
    eng.begin_sub_game(1)
    return eng


def test_reveal_landing_after_a_technical_loss_does_not_raise(engine):
    engine.build_own_step()
    engine.sent_commit()
    # ...the opponent's push lands while `link.reveal` is still in flight.
    engine.declare_technical(engine.other, "turn timeout (180s)")

    engine.sent_reveal()          # must not raise

    assert engine.end is not None and engine.end.ending == "technical_loss"


def test_a_finished_sub_game_builds_no_further_step(engine):
    engine.declare_technical(engine.other, "turn timeout (180s)")

    assert engine.build_own_step() == {}, (
        "an empty package is a no-op for _send_package: no commit, no event")


def test_the_ending_that_was_already_recorded_is_never_overwritten(engine):
    engine.declare_technical(engine.other, "first cause")
    engine.sent_reveal()
    engine.declare_technical(engine.other, "second cause")

    assert engine.end.cause == "first cause"


def test_illegal_play_inside_a_live_sub_game_still_raises():
    """The strictness that catches real logic bugs must survive the fix."""
    m = GamePhaseMachine()
    with pytest.raises(IllegalTransitionError):
        m.transition(COMMITTING)      # cannot skip COMPUTING_MOVE
