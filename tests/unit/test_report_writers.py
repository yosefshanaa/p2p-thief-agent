"""Artifact writers and the signed result builder."""

import json

from p2p_pursuit.report.artifacts import write_config_copy, write_declaration, write_result
from p2p_pursuit.report.results import build_result, sub_game_row


def rows():
    return [sub_game_row(index=1, ending="capture", winner="police", cause="claim",
                         police_score=20, thief_score=5, moves_played=9,
                         github_commit="abc", audit_verdict="Verified OK"),
            sub_game_row(index=2, ending="survival", winner="thief", cause="35 steps",
                         police_score=5, thief_score=10, moves_played=35,
                         github_commit="abc", audit_verdict="Verified OK")]


def test_build_result_totals_and_fields():
    r = build_result(game_uid="u", game_id="g", my_group={"group_id": "a"},
                     opp_group={"group_id": "b"}, sub_games=rows(),
                     police_total=25, thief_total=15, tie_score=2, tokens_used=123,
                     github_commit="abc", my_role="police", mutual_agreement=True)
    assert r["series_winner"] == "police" and r["my_total"] == 25
    assert r["tokens_used"] == 123 and r["github_commit"] == "abc"
    assert r["sub_games"][0]["cop_score"] == 20 and r["result_sha256"]


def test_tie_series_pays_tie_score():
    r = build_result(game_uid="u", game_id="g", my_group={}, opp_group={},
                     sub_games=[], police_total=30, thief_total=30, tie_score=2,
                     tokens_used=0, github_commit="x", my_role="thief",
                     mutual_agreement=True)
    assert r["series_winner"] == "tie" and r["my_total"] == 2 == r["opponent_total"]


def test_writers_produce_appendix_f_names(tmp_path):
    write_declaration(tmp_path, "gid", {"report_type": "declaration"})
    write_config_copy(tmp_path, "gid", 2, {"grid": 7}, "uid")
    write_result(tmp_path, "gid", {"report_type": "game_result"})
    assert (tmp_path / "declaration_gid.json").exists()
    cfg = json.loads((tmp_path / "config_gid_g02.json").read_text())
    assert cfg["config"] == {"grid": 7} and cfg["game_uid"] == "uid"
    assert (tmp_path / "result_gid.json").exists()
