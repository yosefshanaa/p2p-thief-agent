"""Config contract, handshake compatibility, declarations, artifact naming."""

from pathlib import Path

from p2p_pursuit.domain import declarations, negotiation
from p2p_pursuit.domain.game_ids import config_name, declaration_name, log_name, result_name
from p2p_pursuit.shared.config import load_role
from tests.conftest import make_peer, make_shared

BASE = Path(__file__).resolve().parent.parent.parent


def test_both_roles_load_identical_constitutions():
    shared_p, peer_p = load_role(BASE / "config" / "police")
    shared_t, peer_t = load_role(BASE / "config" / "thief")
    assert shared_p.sha256 == shared_t.sha256          # byte-identical rule (#11)
    assert peer_p.my_port == 8802 and peer_t.my_port == 8801
    assert shared_p.grid_size >= 7 and shared_p.first_mover == "thief"
    assert shared_p.max_barriers >= 14 and shared_p.survival_threshold >= 35
    assert peer_p.email_recipient.startswith("rmisegal+")


def test_handshake_and_compatibility():
    shared = make_shared()
    mine = negotiation.handshake_payload(shared, make_peer("police"), role="police",
                                         game_id="g", game_uid="u", counted=True,
                                         prior_counted_games=1)
    theirs = negotiation.handshake_payload(shared, make_peer("thief"), role="thief",
                                           game_id="g", game_uid="u", counted=True,
                                           prior_counted_games=0)
    assert negotiation.check_compatibility(mine, theirs, num_games=6) == []
    assert mine["prior_counted_games"] == 1  # truthful declaration (#37)


def test_compatibility_refusals():
    shared, other = make_shared(), make_shared(**{"world.hint_max_words": 20})
    mine = negotiation.handshake_payload(shared, make_peer(), role="police",
                                         game_id="g", game_uid="u", counted=True,
                                         prior_counted_games=0)
    theirs = negotiation.handshake_payload(other, make_peer("thief"), role="thief",
                                           game_id="g", game_uid="u", counted=True,
                                           prior_counted_games=0)
    problems = negotiation.check_compatibility(mine, theirs, num_games=6)
    assert any("constitution mismatch" in p for p in problems)
    same_role = dict(theirs, role="police", config_sha256=mine["config_sha256"])
    assert any("both peers claim" in p for p in
               negotiation.check_compatibility(mine, same_role, num_games=6))
    assert any("counted match requires 6" in p for p in
               negotiation.check_compatibility(mine, theirs, num_games=1))


def test_declaration_contents():
    me = declarations.team_block(group_id="g1", group_name="G", members=["1"],
                                 repos={"cop": "u1", "thief": "u2"},
                                 mcp_url="http://x/mcp", llm_model="")
    decl = declarations.build_declaration(
        game_uid="u", game_id="g", game_number=3, config_sha256="c" * 64,
        scent_model_sha256="s" * 64, token_cap=200000, me=me, opponent=None)
    assert decl["game_number"] == 3 and decl["token_cap"] == 200000
    assert me["hardware"]["cpu_cores"] >= 1
    assert me["github_commit"] and me["code_version"]
    assert decl["declaration_sha256"]


def test_artifact_names_from_appendix_f():
    assert declaration_name("gid") == "declaration_gid.json"
    assert config_name("gid", 3) == "config_gid_g03.json"
    assert log_name("gid", 12) == "log_gid_g12.json"
    assert result_name("gid") == "result_gid.json"
