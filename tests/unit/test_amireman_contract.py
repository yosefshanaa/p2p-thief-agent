"""Conformance to team `amireman`'s interoperability guide.

Three behaviours their contract specifies that our defaults get right for every
*other* opponent. Each is invisible in a healthy-looking short run and expensive
exactly once: a withheld claim forfeits a capture we earned, a signed series
length refuses the handshake, and their consensus envelope lands on the tool our
per-sub-game audits use.
"""

from __future__ import annotations

import pytest

from p2p_pursuit.domain.rules import Decision
from p2p_pursuit.peer.turn_engine import TurnEngine
from p2p_pursuit.report.consensus import CONSENSUS_CLAIM, consensus_envelope
from p2p_pursuit.shared.config import apply_env_overrides

from ..conftest import ScriptedBrain, make_peer, make_shared


# -- §5: the claim is protocol, not strategy ---------------------------------
def _police_engine(**peer_kw) -> TurnEngine:
    engine = TurnEngine("police", make_shared(), make_peer("police", **peer_kw), seed=1)
    # Never claims of its own accord: any claim seen below is the flag's doing.
    engine.brain = ScriptedBrain([Decision(move="S") for _ in range(6)])
    return engine


def test_default_police_withholds_the_claim() -> None:
    """Our own dialect spends a claim deliberately - it discloses our cell."""
    engine = _police_engine()
    assert "claim" not in engine.build_own_step()["reveal"]


def test_always_claim_declares_the_post_move_cell_every_turn() -> None:
    """Their §5: every Cop turn, no gating, and the cell is the Cop's own."""
    engine = _police_engine(always_claim=True)
    for _ in range(3):
        package = engine.build_own_step()
        claim = package["reveal"].get("claim")
        assert claim is not None, "a gated claim forfeits captures under their §5"
        assert claim["cell"] == list(engine.own_pos)
        engine.sent_commit()
        engine.sent_reveal()


def test_always_claim_covers_stay_and_barrier_turns() -> None:
    """Their §5 names both explicitly: "on every Cop turn, including STAY and
    barrier turns". A barrier turn is the trap - it forgoes movement and carries
    `barrier_placed`, so it is the turn most likely to be treated as claimless."""
    engine = _police_engine(always_claim=True)
    engine.brain = ScriptedBrain([
        Decision(move="STAY"),
        Decision(move="STAY", barrier=(6, 6)),
    ])
    for expect_barrier in (None, [6, 6]):
        package = engine.build_own_step()
        claim = package["reveal"].get("claim")
        assert claim is not None
        assert claim["cell"] == list(engine.own_pos)
        # §5: the barrier cell is never the claim - the claim is the Cop's own.
        if expect_barrier is not None:
            assert claim["cell"] != expect_barrier
        engine.sent_commit()
        engine.sent_reveal()


def test_always_claim_is_off_for_every_other_opponent() -> None:
    """It changes what our pursuer discloses, so it must never be a default."""
    assert make_peer("police").always_claim is False


# -- §15: --games must not move the signed num_games -------------------------
def test_signed_num_games_survives_a_short_run(monkeypatch) -> None:
    """Signing the short count fails the terms comparison on the very run meant
    to prove the terms agree."""
    from p2p_pursuit.infra.interop_codec import interop_terms

    monkeypatch.setenv("P2P_SIGNED_NUM_GAMES", "6")
    peer = apply_env_overrides(make_peer("police"))
    assert peer.signed_num_games == 6
    # A 2-sub-game smoke run still signs the agreed series length.
    assert interop_terms(make_shared(), num_games=peer.signed_num_games)["num_games"] == 6
    assert interop_terms(make_shared(), num_games=2)["num_games"] == 2


def test_signed_num_games_rejects_a_malformed_value(monkeypatch) -> None:
    monkeypatch.setenv("P2P_SIGNED_NUM_GAMES", "six")
    with pytest.raises(ValueError, match="positive integer"):
        apply_env_overrides(make_peer("police"))


def test_signed_num_games_defaults_to_what_is_played() -> None:
    assert make_peer("police").signed_num_games is None


# -- §3: a mutually agreed game_id label -------------------------------------
def test_game_id_label_overrides_the_derived_id(monkeypatch) -> None:
    monkeypatch.setenv("P2P_GAME_ID", "AHK-DEMO1")
    assert apply_env_overrides(make_peer("police")).game_id_label == "AHK-DEMO1"


def test_no_label_means_derive_it() -> None:
    assert make_peer("police").game_id_label == ""


def test_the_label_reaches_the_consensus_digest() -> None:
    """Their §3: `game_id` is part of the consensus hash, so a label set on one
    side only is a guaranteed mismatch at the end of a clean series."""
    from p2p_pursuit.report.consensus import consensus_document, consensus_sha

    rows = [{"index": 1, "ending": "survival",
             "roles": {"ahk-yosi": "police", "amireman": "thief"},
             "score": {"ahk-yosi": 5, "amireman": 10}, "winner_group": "amireman"}]
    derived = consensus_sha(consensus_document(
        game_id="ahk-yosi-vs-amireman", game_uid="u", rows=rows))
    labelled = consensus_sha(consensus_document(
        game_id="AHK-DEMO1", game_uid="u", rows=rows))
    assert derived != labelled


def test_the_uid_is_never_overridden_by_a_label() -> None:
    """It is derived from the terms and both slugs - the one value that proves
    the two peers signed the same document."""
    from p2p_pursuit.domain.game_ids import reference_game_uid

    terms = {"board_size": 7, "num_games": 6}
    assert reference_game_uid(terms, "ahk-yosi", "amireman") == \
        reference_game_uid(terms, "amireman", "ahk-yosi")


# -- §10.3: the consensus envelope shares a tool with the audits -------------
class _FakeService:
    """Just enough of PeerService for the bridge's audit path."""

    def __init__(self) -> None:
        import threading

        from p2p_pursuit.domain.rules import Decision  # noqa: F401

        self._cv = threading.Condition()
        self.audit_packages: dict = {}
        self.audit_verdicts: dict = {}
        self.engine = TurnEngine("police", make_shared(), make_peer("police"), seed=1)

    def locked(self):
        return self._cv


def _bridge() -> tuple:
    from p2p_pursuit.infra.interop_bridge import ReferenceBridge

    service = _FakeService()
    return ReferenceBridge(service, link=None, grid_size=7, terms={}, identity={}), service


def test_consensus_envelope_is_not_filed_as_a_sub_game_audit() -> None:
    """It carries no records: auditing it would write an empty-log verdict over
    the last sub-game's real one and lose a finished series."""
    bridge, service = _bridge()
    sha = "b" * 64
    bridge.on_submit_audit(consensus_envelope(sender="thief", sha=sha))
    assert bridge.peer_consensus_sha == sha
    assert service.audit_packages == {} and service.audit_verdicts == {}


def test_a_real_audit_package_still_reaches_the_audit_path() -> None:
    bridge, service = _bridge()
    bridge.on_submit_audit({"sender": "thief", "records": [], "result_claim": "survival"})
    assert bridge.peer_consensus_sha is None
    assert service.engine.sub_game in service.audit_verdicts


def test_a_mismatched_sender_role_still_yields_the_digest() -> None:
    """Deliberate leniency: the role is bookkeeping the connection already
    implies, and a clean series should not fail to confirm over it."""
    bridge, _ = _bridge()
    envelope = consensus_envelope(sender="police", sha="c" * 64)
    bridge.on_submit_audit(envelope)  # our engine plays police, so peer_role is thief
    assert bridge.peer_consensus_sha == "c" * 64


def test_a_malformed_digest_reads_as_no_digest_received() -> None:
    bridge, _ = _bridge()
    bridge.on_submit_audit({"sender": "thief", "records": [],
                            "result_claim": CONSENSUS_CLAIM, "consensus_sha": "nope"})
    assert bridge.peer_consensus_sha is None
