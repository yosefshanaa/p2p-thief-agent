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


def test_board_cells_scent_overlay():
    """Opponent scent (a legitimate observation) renders as a violet cell
    outline; cells without scent - and boards without any scent snapshot -
    keep the plain grid outline."""
    status = {"board_size": 3, "belief": [[0.0] * 3 for _ in range(3)],
              "barriers": [], "own_pos": [0, 0], "role": "police",
              "opp_scent": [[0.0, 0.0, 0.0], [0.0, 0.81, 0.0], [0.0, 0.0, 0.0]]}
    cells = board_cells(status)
    assert cells[1][1]["outline"] != "#cccccc" and cells[1][1]["width"] > 1
    assert cells[0][2]["outline"] == "#cccccc" and cells[0][2]["width"] == 1
    del status["opp_scent"]
    assert all(c["outline"] == "#cccccc" and c["width"] == 1
               for row in board_cells(status) for c in row)


def test_belief_stats_and_info_lines():
    from p2p_pursuit.gui.view_model import belief_stats, info_lines

    peak_at, entropy = belief_stats([[0.25] * 2, [0.25] * 2])
    assert entropy == 2.0  # uniform over 4 cells = log2(4) bits
    assert belief_stats([[0.0, 0.9], [0.05, 0.05]])[0] == (0, 1)
    status = {"role": "thief", "sub_game": 2, "phase": "WAITING", "my_steps": 3,
              "opp_steps": 3, "barriers_used": 0, "trust": 0.4, "tokens_used": 0,
              "belief": [[0.0, 1.0], [0.0, 0.0]],
              "hints": [{"dir": "sent", "hint": "going north"}],
              "end": {"ending": "survival", "winner": "thief"}}
    lines = info_lines(status)
    text = "\n".join(lines)
    assert "hint trust: 0.40" in text and "[sent] going north" in text
    assert "peak @ (0, 1)" in text and "END: survival" in text


def test_board_cells_marks_belief_argmax_ring():
    from p2p_pursuit.gui.view_model import board_cells

    status = {"board_size": 2, "belief": [[0.1, 0.7], [0.1, 0.1]],
              "barriers": [], "own_pos": [1, 1], "role": "police"}
    cells = board_cells(status)
    rings = [(r, c) for r in range(2) for c in range(2) if cells[r][c]["ring"]]
    assert rings == [(0, 1)]


def test_legend_covers_every_board_glyph():
    import re

    from p2p_pursuit.gui.view_model import legend_items

    items = legend_items()
    labels = " ".join(label for _, label in items)
    for needed in ("belief", "peak", "scent", "barrier", "you"):
        assert needed in labels
    assert all(re.fullmatch(r"#[0-9a-f]{6}", color) for color, _ in items)


def test_end_banner_color_reflects_outcome_for_this_role():
    end = {"ending": "capture", "winner": "police"}
    assert banner({"end": end, "role": "police"})[1] == "#22aa44"  # we won
    assert banner({"end": end, "role": "thief"})[1] == "#cc4444"   # we lost
    tie = {"ending": "tie", "winner": None}
    assert banner({"end": tie, "role": "police"})[1] == "#4488ff"  # neutral


def test_own_cell_uses_role_accent():
    from p2p_pursuit.gui.view_model import ROLE_ACCENT, board_cells

    status = {"board_size": 2, "belief": [[0.0] * 2 for _ in range(2)],
              "barriers": [], "own_pos": [0, 0], "role": "thief"}
    assert board_cells(status)[0][0]["fill"] == ROLE_ACCENT["thief"]
    assert ROLE_ACCENT["police"] != ROLE_ACCENT["thief"]


def test_board_cells_local_truth_only():
    """The live board renders belief, barriers and OUR pos - opponent pos nowhere."""
    status = {"board_size": 3, "belief": [[0.1] * 3 for _ in range(3)],
              "barriers": [[0, 1]], "own_pos": [2, 2], "role": "police"}
    cells = board_cells(status)
    glyphs = {cells[r][c]["text"] for r in range(3) for c in range(3)}
    assert glyphs <= {"", "#", "P"}          # never a thief marker
    assert cells[0][1]["fill"] == "#222222"  # barrier
    assert cells[2][2]["text"] == "P"        # our own cell
