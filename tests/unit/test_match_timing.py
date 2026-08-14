"""A finished match must be able to say when it started and when it ended.

Before this, `declaration.ended_at` was set to None by the builder and written
back by nobody, so every filed declaration - the artifact the lecturer receives
- claimed a start and no end; and `log_*.json` carried no clock at all, so
"when did sub-game 4 run" was answerable only from file mtimes, which are not
sealed, not exchanged, and do not survive a copy.
"""

from __future__ import annotations

from p2p_pursuit.domain.crypto import REFERENCE, digest
from p2p_pursuit.domain.declarations import (
    build_declaration,
    close_declaration,
    team_block,
)
from p2p_pursuit.peer import audit_bridge, log_manager
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from tests.conftest import make_peer, make_shared


def _declaration() -> dict:
    me = team_block(group_id="ahk-yosi", group_name="ahk-yosi", members=["1"],
                    repos={"cop": "https://x/c"}, mcp_url="http://x/mcp", llm_model="")
    return build_declaration(
        game_uid="u", game_id="g", game_number=1, config_sha256="c" * 64,
        scent_model_sha256="s" * 64, token_cap=200000, me=me, opponent=None)


def test_a_fresh_declaration_has_a_start_and_no_end_yet():
    decl = _declaration()
    assert decl["started_at"] and decl["ended_at"] is None


def test_closing_a_declaration_stamps_the_end_and_re_seals_it():
    decl = close_declaration(_declaration())
    assert decl["ended_at"] >= decl["started_at"]
    body = {k: v for k, v in decl.items() if k != "declaration_sha256"}
    assert decl["declaration_sha256"] == digest(body), "re-stamped, so re-sealed"


def test_closing_accepts_an_explicit_end_time():
    decl = close_declaration(_declaration(), "2026-08-14T17:00:34+00:00")
    assert decl["ended_at"] == "2026-08-14T17:00:34+00:00"


def _pair():
    shared = make_shared(**{"movement_and_barriers.max_moves": 6,
                            "movement_and_barriers.survival_threshold": 6})
    police = TurnEngine("police", shared, make_peer("police", interop_dialect=REFERENCE),
                        seed=1)
    thief = TurnEngine("thief", shared, make_peer("thief", interop_dialect=REFERENCE),
                       seed=2)
    return police, thief


def test_a_sub_game_log_records_its_own_start_and_end():
    police, thief = _pair()
    police.begin_sub_game(1)
    thief.begin_sub_game(1)
    play_sub_game(police, thief)
    package = audit_bridge.audit_package(thief, 1)

    log = log_manager.build_log(thief, [], game_uid="u", game_id="g",
                                audit={}, package=package)
    assert log["started_at"] and log["ended_at"]
    assert log["ended_at"] >= log["started_at"]


def test_the_clock_is_frozen_when_the_sub_game_ends_not_when_the_log_is_written():
    """The log is written after the audit exchange, so reading the clock then
    would time the paperwork rather than the sub-game."""
    police, thief = _pair()
    police.begin_sub_game(1)
    thief.begin_sub_game(1)
    play_sub_game(police, thief)
    first = audit_bridge.audit_package(thief, 1)

    police.begin_sub_game(2)
    thief.begin_sub_game(2)
    play_sub_game(police, thief)

    late = audit_bridge.audit_package(thief, 1)
    assert late["started_at"] == first["started_at"]
    assert late["ended_at"] == first["ended_at"]
    assert audit_bridge.audit_package(thief, 2)["started_at"] >= first["ended_at"]


def test_sub_game_one_is_timed_from_play_not_from_construction():
    """`start_sub_game` runs from the constructor, minutes before the handshake,
    so sub-game 1 otherwise reports a start earlier than the declaration."""
    police, _thief = _pair()
    built_at = police.started_at
    police.mark_started()
    assert police.started_at >= built_at

    police.begin_sub_game(1)
    police.my_records.append({"kind": "step"})
    played_at = police.started_at
    police.mark_started()
    assert police.started_at == played_at, "a sub-game in progress cannot rewind"


def test_their_wire_timestamps_are_kept_and_filed_as_theirs():
    """Their turn stamps ride outside their commitment, so they are untrusted
    as evidence - but they are the only clock sourced from the other side."""
    from p2p_pursuit.infra import interop_codec as codec

    parts = codec.from_turn_message(
        {"sender": "thief", "step": 1, "commit": "a" * 64, "smell_grid": {},
         "timestamp": "2026-08-14T16:57:03+00:00"}, sub_game=1, grid_size=7)
    assert parts["reveal"]["timestamp"] == "2026-08-14T16:57:03+00:00"

    police, _thief = _pair()
    police.begin_sub_game(1)
    police.on_commit(parts["commit"])
    police.on_reveal(parts["reveal"])
    assert police.opp_turn_times == ["2026-08-14T16:57:03+00:00"]

    log = log_manager.build_log(police, [], game_uid="u", game_id="g", audit={},
                                package=audit_bridge.audit_package(police, 1))
    assert log["opponent_turn_timestamps"] == ["2026-08-14T16:57:03+00:00"]


def test_a_native_match_without_wire_stamps_records_none_rather_than_failing():
    police, thief = _pair()
    police.begin_sub_game(1)
    thief.begin_sub_game(1)
    play_sub_game(police, thief)
    package = audit_bridge.audit_package(police, 1)
    log = log_manager.build_log(police, [], game_uid="u", game_id="g", audit={},
                                package=package)
    assert log["opponent_turn_timestamps"]
    assert all(stamp is None for stamp in log["opponent_turn_timestamps"])
