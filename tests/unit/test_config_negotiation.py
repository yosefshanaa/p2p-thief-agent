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


def test_deployment_env_overrides_the_committed_port_and_url(monkeypatch, tmp_path):
    """A container cannot know its own port or the opponent's URL at build time:
    the platform injects $PORT and the opponent's address is exchanged hours
    before the match. Both must beat the committed TOML, or a hosted peer binds
    the wrong port and never comes up.
    """
    from pathlib import Path

    from p2p_pursuit.shared.config import load_role

    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("P2P_OPPONENT_URL", "https://their-host.example/mcp")
    _shared, peer = load_role(Path("config/police"))
    assert peer.my_port == 8080
    assert peer.opponent_url == "https://their-host.example/mcp"


def test_a_blank_or_junk_port_leaves_the_configured_one_alone(monkeypatch):
    """An empty PORT is common in shells and CI; it must not silently become 0."""
    from pathlib import Path

    from p2p_pursuit.shared.config import load_peer
    from p2p_pursuit.shared.config_env import apply_env_overrides

    peer = load_peer(Path("config/police/game.toml"))
    for junk in ("", "   ", "not-a-port"):
        monkeypatch.setenv("PORT", junk)
        assert apply_env_overrides(peer).my_port == peer.my_port
    monkeypatch.setenv("P2P_MY_PORT", "9001")
    monkeypatch.setenv("PORT", "8080")
    assert apply_env_overrides(peer).my_port == 9001, "the explicit name wins"


def test_the_environment_can_force_draft_email_for_a_hosted_rehearsal(monkeypatch):
    """A deployed peer must be incapable of mailing the lecturer from a test.
    Editing the committed config to achieve that invites shipping the edit, so
    the environment overrides it - and only to a value the sender understands.
    """
    from pathlib import Path

    from p2p_pursuit.shared.config import load_peer
    from p2p_pursuit.shared.config_env import apply_env_overrides

    peer = load_peer(Path("config/police/game.toml"))
    assert peer.email_mode == "send", "the committed config stays league-ready"

    monkeypatch.setenv("P2P_EMAIL_MODE", "draft")
    monkeypatch.setenv("P2P_EMAIL_RECIPIENT", "apexmediamind@gmail.com")
    safe = apply_env_overrides(peer)
    assert safe.email_mode == "draft"
    assert safe.email_recipient == "apexmediamind@gmail.com"

    monkeypatch.setenv("P2P_EMAIL_MODE", "nonsense")
    assert apply_env_overrides(peer).email_mode == "send", "junk must not disable reporting"


def test_the_interop_contract_is_settable_per_opponent_without_a_rebuild(monkeypatch):
    """Dialect, alternation, per-sub-game handshake and the enclosure rule are
    negotiated with each team hours before a match. A hosted peer cannot be
    rebuilt for every opponent, so they belong in the environment next to the
    opponent's URL - not in a committed file.
    """
    from pathlib import Path

    from p2p_pursuit.shared.config import load_peer
    from p2p_pursuit.shared.config_env import apply_env_overrides

    peer = load_peer(Path("config/police/game.toml"))
    assert (peer.interop_dialect, peer.alternate_roles) == ("native", False)
    assert peer.claim_enclosure is True, "our own doctrine is the default"

    monkeypatch.setenv("P2P_DIALECT", "reference")
    monkeypatch.setenv("P2P_ALTERNATE_ROLES", "true")
    monkeypatch.setenv("P2P_HANDSHAKE_PER_SUB_GAME", "1")
    monkeypatch.setenv("P2P_CLAIM_ENCLOSURE", "false")
    tuned = apply_env_overrides(peer)
    assert tuned.interop_dialect == "reference"
    assert tuned.alternate_roles is True and tuned.handshake_per_sub_game is True
    assert tuned.claim_enclosure is False


def test_a_junk_dialect_is_ignored_rather_than_played(monkeypatch):
    """A typo must not silently put us on a wire contract nobody speaks."""
    from pathlib import Path

    from p2p_pursuit.shared.config import load_peer
    from p2p_pursuit.shared.config_env import apply_env_overrides

    peer = load_peer(Path("config/police/game.toml"))
    monkeypatch.setenv("P2P_DIALECT", "referrence")
    assert apply_env_overrides(peer).interop_dialect == "native"


def test_a_negotiated_setting_can_be_adopted_without_editing_the_constitution(monkeypatch):
    """`setting` only flavours hint landmarks, but a reference-derived peer
    compares the agreed terms for exact equality and refuses on any mismatch.
    Adopting an opponent's value must not mean editing the committed file and
    risking that edit reaching a later match against someone else.
    """
    from pathlib import Path

    from p2p_pursuit.shared.config import load_shared

    assert load_shared(Path("config/police/game.json")).map_area == "New York"
    monkeypatch.setenv("P2P_MAP_AREA", "Haifa")
    adopted = load_shared(Path("config/police/game.json"))
    assert adopted.map_area == "Haifa"
    assert adopted.raw["world"]["map_area"] == "Haifa", "the digest is taken after the override"
