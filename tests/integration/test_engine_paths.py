"""Forced end-to-end scenarios through the real protocol paths."""

from p2p_pursuit.domain.protocol import PRIVATE_FIELDS
from p2p_pursuit.domain.rules import Decision
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from tests.conftest import ScriptedBrain, make_peer, make_shared


def engines(shared, police_brain=None, thief_brain=None):
    police = TurnEngine("police", shared, make_peer("police"), brain=police_brain, seed=1)
    thief = TurnEngine("thief", shared, make_peer("thief"), brain=thief_brain, seed=2)
    return police, thief


def test_reveal_never_leaks_private_fields():
    shared = make_shared()
    police, thief = engines(shared)
    package = thief.build_own_step()
    for field in PRIVATE_FIELDS:
        assert field not in package["reveal"], field
    assert "hash" in package["reveal"] and "scent" in package["reveal"]


def test_survival_path():
    shared = make_shared(**{"movement_and_barriers.max_moves": 4,
                            "movement_and_barriers.survival_threshold": 4})
    police, thief = engines(shared)
    play_sub_game(police, thief)
    assert police.end.ending == "survival" and thief.end.ending == "survival"
    assert police.end.winner == "thief" == thief.end.winner


def test_capture_by_confirmed_claim():
    """Police walks onto the thief (scripted) and claims - thief must confess."""
    shared = make_shared(**{"board_and_agents.thief_start": [0, 1],
                            "board_and_agents.cop_start": [0, 0]})
    thief_brain = ScriptedBrain([Decision(move="STAY")] * 40)
    police_brain = ScriptedBrain([Decision(move="E")] * 40, claim_always=True)
    police, thief = engines(shared, police_brain, thief_brain)
    play_sub_game(police, thief)
    assert police.end.ending == "capture" and police.end.winner == "police"
    assert thief.end.ending == "capture"


def test_capture_by_barrier_onto_thief():
    shared = make_shared(**{"board_and_agents.thief_start": [0, 1],
                            "board_and_agents.cop_start": [0, 0]})
    thief_brain = ScriptedBrain([Decision(move="STAY")] * 40)
    police_brain = ScriptedBrain([Decision(move="STAY", barrier=(0, 1))])
    police, thief = engines(shared, police_brain, thief_brain)
    play_sub_game(police, thief)
    assert thief.end.ending == "capture" and thief.end.cause.startswith("barrier")
    assert police.end.ending == "capture"


def test_capture_by_enclosure():
    """Thief pinned in the corner behind barriers - forced honest confession (#47)."""
    shared = make_shared(**{"board_and_agents.thief_start": [0, 0],
                            "board_and_agents.cop_start": [2, 2]})
    police_brain = ScriptedBrain([Decision(move="STAY", barrier=(2, 1)),
                                  Decision(move="N"), Decision(move="N"),
                                  Decision(move="W"),
                                  Decision(move="STAY", barrier=(0, 1)),
                                  Decision(move="S"), Decision(move="W"),
                                  Decision(move="STAY", barrier=(1, 0))] +
                                 [Decision(move="STAY")] * 30)
    thief_brain = ScriptedBrain([Decision(move="STAY")] * 40)
    police, thief = engines(shared, police_brain, thief_brain)
    play_sub_game(police, thief)
    assert thief.end.ending == "capture" and thief.end.cause == "enclosed"


def test_denied_claim_reveals_police_and_excludes_cell():
    shared = make_shared(**{"board_and_agents.thief_start": [6, 6],
                            "board_and_agents.cop_start": [0, 0],
                            "movement_and_barriers.max_moves": 3,
                            "movement_and_barriers.survival_threshold": 3})
    police_brain = ScriptedBrain([Decision(move="E")] * 5, claim_always=True)
    police, thief = engines(shared, police_brain, ScriptedBrain())
    play_sub_game(police, thief)
    # thief survived; the wrong claims must have zeroed police belief on claimed cells
    assert police.end.ending == "survival"
    assert police.belief.grid[0][1] == 0.0
    # and the thief's belief collapsed onto the claimed police cell at claim time
    assert thief.belief.mass_in({(0, r) for r in range(7)}) > 0.5


def test_turn_timeout_becomes_technical_loss():
    shared = make_shared()
    police, _thief = engines(shared)
    police.declare_technical(police.other, "turn timeout (180s)")
    assert police.end.ending == "technical_loss" and police.end.winner == "police"
    assert police.score_table.score(police.end.ending) == (0, 0)  # both zeroed
