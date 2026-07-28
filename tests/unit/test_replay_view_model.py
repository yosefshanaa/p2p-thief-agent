"""Replay verification logic + the live GUI's local-truth invariant."""

from p2p_pursuit.domain.audit import TAMPERED, VERIFIED_OK
from p2p_pursuit.gui.replay_data import frames, timeline, verdict_of
from p2p_pursuit.gui.view_model import banner, board_cells, heat_hex
from p2p_pursuit.peer import audit_bridge, log_manager
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from tests.conftest import make_peer, make_shared


def make_log():
    shared = make_shared(**{"movement_and_barriers.max_moves": 8,
                            "movement_and_barriers.survival_threshold": 8})
    police = TurnEngine("police", shared, make_peer("police"), seed=3)
    thief = TurnEngine("thief", shared, make_peer("thief"), seed=4)
    play_sub_game(police, thief)
    verdict, violations = audit_bridge.run_audit(police, audit_bridge.audit_package(thief))
    return log_manager.build_log(police, thief.my_records, game_uid="u", game_id="gid",
                                 audit={"mine_of_them": {"verdict": verdict}})


def test_clean_log_verifies_and_orders_thief_first():
    log = make_log()
    verdict, mine, theirs = verdict_of(log)
    assert verdict == VERIFIED_OK and all(mine) and all(theirs)
    items = timeline(log)
    assert items[0]["role"] == "thief" and items[1]["role"] == "police"
    assert [i["step"] for i in items] == sorted(i["step"] for i in items)


def test_tampered_log_flips_verdict():
    log = make_log()
    for record in log["opponent_records"]:
        if record["kind"] == "step":
            record["pos_after"] = [0, 0]
            break
    assert verdict_of(log)[0] == TAMPERED


def test_frames_accumulate_positions_and_barriers():
    log = make_log()
    fs = frames(log)
    assert fs, "no frames"
    assert set(fs[-1]["positions"]) <= {"police", "thief"}


def test_view_model_banner_and_colors():
    assert banner({"end": None, "my_turn": True})[0] == "YOUR TURN"
    assert banner({"end": None, "my_turn": False})[0] == "LOCKED"
    text, _ = banner({"end": {"ending": "capture", "winner": "police"}, "my_turn": False})
    assert "CAPTURE" in text
    assert heat_hex(0.0, 1.0) == "#ffffff"
    assert heat_hex(1.0, 1.0) == "#ff2626"


def test_board_cells_local_truth_only():
    """The live board renders belief, barriers and OUR pos - opponent pos nowhere."""
    status = {"board_size": 3, "belief": [[0.1] * 3 for _ in range(3)],
              "barriers": [[0, 1]], "own_pos": [2, 2], "role": "police"}
    cells = board_cells(status)
    glyphs = {cells[r][c]["text"] for r in range(3) for c in range(3)}
    assert glyphs <= {"", "#", "P"}          # never a thief marker
    assert cells[0][1]["fill"] == "#222222"  # barrier
    assert cells[2][2]["text"] == "P"        # our own cell
