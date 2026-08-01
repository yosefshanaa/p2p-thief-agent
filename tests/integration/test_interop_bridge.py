"""The reference-dialect bridge, driven by a stand-in for their peer.

Every shape here was taken from the reference implementation's own source and
confirmed against it in a live warm-up match (RUNBOOK 3b): our peer played a
full sub-game against an unmodified reference peer, its audit returned
``log_verified: true`` on our records, and ours returned ``Verified OK`` on
theirs. These tests keep that interoperability from regressing silently.
"""

from __future__ import annotations

from p2p_pursuit.domain.audit import TAMPERED, VERIFIED_OK
from p2p_pursuit.domain.crypto import REFERENCE, reference_commit, seal
from p2p_pursuit.gui import replay_data
from p2p_pursuit.infra.interop_audit import audit_reference_log
from p2p_pursuit.infra.interop_bridge import ReferenceBridge
from p2p_pursuit.report import results


class _FakeReferencePeer:
    """Records what our bridge pushes at their tool surface."""

    def __init__(self):
        self.turns, self.agreements, self.audits = [], [], []

    def list_tools(self, timeout=None):
        return ["negotiate", "receive_turn", "submit_audit", "receive_control"]

    def negotiate(self, signed, timeout=None):
        self.agreements.append(signed)
        return {"ok": True}

    def receive_turn(self, message, timeout=None):
        self.turns.append(message)
        return {"ok": True}

    def submit_audit(self, payload, timeout=None):
        self.audits.append(payload)
        return {"ok": True}


class _FakeEngine:
    def __init__(self, role="police"):
        self.role, self.other = role, "thief" if role == "police" else "police"
        self.sub_game, self.opp_steps = 1, 0
        self.opp_hashes: list[str] = []
        self.end = None
        self.technical: list[tuple] = []

    def declare_technical(self, offender, reason):
        self.technical.append((offender, reason))


class _FakeService:
    def __init__(self, engine=None):
        import threading

        self.engine = engine or _FakeEngine()
        self.commits, self.reveals = [], []
        self.audit_packages, self.audit_verdicts = {}, {}
        self.reveal_response = {"ok": True, "events": []}
        self._cv = threading.Condition()

    def receive_commit(self, msg):
        self.commits.append(msg)
        return {"ack": True}

    def receive_reveal(self, pub):
        self.reveals.append(pub)
        return self.reveal_response

    def locked(self):
        return self._cv


def _bridge(service=None, peer=None):
    service = service or _FakeService()
    peer = peer or _FakeReferencePeer()
    bridge = ReferenceBridge(service, peer, grid_size=7, terms={"board_size": 7},
                             identity={"group_id": "ahk-yosi"})
    return bridge, service, peer


def _reveal(**over):
    base = {"kind": "step", "role": "police", "sub_game": 1, "step": 1, "barrier": None,
            "hint": "by the park", "scent": [[0.0] * 7 for _ in range(7)],
            "hash": "a" * 64}
    return {**base, **over}


# -- outbound ----------------------------------------------------------------
def test_commit_is_held_back_and_folded_into_the_turn_message():
    """Their protocol has no separate commit call: the hash rides the turn."""
    bridge, _, peer = _bridge()
    bridge.commit({"hash": "b" * 64})
    assert peer.turns == []  # nothing on the wire yet
    bridge.reveal(_reveal())
    assert len(peer.turns) == 1
    assert peer.turns[0]["commit"] == "b" * 64
    assert peer.turns[0]["sender"] == "police"


def test_owed_claim_answer_rides_the_following_turn_then_clears():
    bridge, _, peer = _bridge()
    bridge.event({"public": {"kind": "capture_answer", "claim_cell": [1, 2],
                             "answer": False}})
    bridge.commit({"hash": "b" * 64})
    bridge.reveal(_reveal())
    assert peer.turns[0]["claim_response"] == {"claim": [1, 2], "caught": False}
    bridge.commit({"hash": "c" * 64})
    bridge.reveal(_reveal(step=2))
    assert peer.turns[1]["claim_response"] is None


def test_handshake_pushes_a_signed_agreement_and_waits_for_theirs():
    bridge, _, peer = _bridge()
    their_terms = {"board_size": 7}
    nonce = "0" * 32
    bridge.on_negotiate({"terms": their_terms, "nonce": nonce,
                         "signature": reference_commit(their_terms, nonce),
                         "identity": {"group_id": "segal-thief-team"}})
    theirs = bridge.handshake({"role": "police", "config_sha256": "x",
                               "scent_model_sha256": "y", "first_mover": "thief"},
                              timeout=5)
    sent = peer.agreements[0]
    assert sent["terms"] == {"board_size": 7}
    assert reference_commit(sent["terms"], sent["nonce"]) == sent["signature"]
    assert theirs["group_id"] == "segal-thief-team"
    assert theirs["config_sha256"] == "x"  # terms matched, so the locks mirror


def test_handshake_withholds_the_locks_when_their_terms_differ():
    bridge, _, peer = _bridge()
    bridge.on_negotiate({"terms": {"board_size": 9}, "nonce": "0" * 32,
                         "signature": "wrong", "identity": {}})
    theirs = bridge.handshake({"role": "police", "config_sha256": "x",
                               "scent_model_sha256": "y"}, timeout=5)
    assert theirs["terms_match"] is False
    assert "config_sha256" not in theirs  # check_compatibility will refuse


# -- inbound -----------------------------------------------------------------
def test_their_turn_is_split_into_our_commit_and_reveal():
    bridge, service, _ = _bridge()
    bridge.on_receive_turn({"step": 1, "sender": "thief", "hint": "river",
                            "smell_grid": {"1,1": 0.9}, "commit": "c" * 64,
                            "timestamp": "t", "barrier_placed": None,
                            "capture_claim": None, "claim_response": None,
                            "win_claim": None})
    assert service.commits[0]["hash"] == "c" * 64
    assert service.reveals[0]["hint"] == "river"
    assert service.reveals[0]["scent"][1][1] == 0.9


def test_a_role_collision_is_caught_on_the_first_turn():
    """Their agreement carries no role, so this is the only place to notice."""
    engine = _FakeEngine(role="police")
    bridge, service, _ = _bridge(service=_FakeService(engine))
    out = bridge.on_receive_turn({"step": 1, "sender": "police", "hint": "",
                                  "smell_grid": {}, "commit": "c" * 64,
                                  "timestamp": "t"})
    assert out["ok"] is False
    assert engine.technical and "both peers claim role" in engine.technical[0][1]
    assert service.commits == []  # never reached the engine


def test_their_unsealed_survival_claim_below_threshold_is_a_technical_loss():
    engine = _FakeEngine()
    engine.opp_steps = 3
    engine.shared = type("S", (), {"survival_threshold": 35})()
    bridge, _, _ = _bridge(service=_FakeService(engine))
    bridge.on_receive_turn({"step": 1, "sender": "thief", "hint": "", "smell_grid": {},
                            "commit": "c" * 64, "timestamp": "t",
                            "win_claim": {"type": "survival"}})
    assert engine.technical and "survival claimed" in engine.technical[0][1]


def test_their_audit_is_verified_on_their_terms_and_filed_for_the_pipeline():
    engine = _FakeEngine()
    payload = {"step": 1, "position": [3, 3], "hint": "x"}
    nonce = "0" * 32
    record = {"payload": payload, "nonce": nonce,
              "commit": reference_commit(payload, nonce)}
    engine.opp_hashes = [record["commit"]]
    bridge, service, _ = _bridge(service=_FakeService(engine))
    bridge.on_submit_audit({"sender": "thief", "records": [record]})
    assert service.audit_verdicts[1]["verdict"] == VERIFIED_OK
    assert service.audit_packages[1]["records"] == [record]


def test_our_audit_package_is_resealed_into_their_envelope():
    bridge, service, peer = _bridge()
    sealed, _ = seal({"kind": "step", "step": 1}, REFERENCE)
    bridge.audit({"role": "police", "records": [sealed]})
    sent = peer.audits[0]["records"][0]
    assert set(sent) == {"payload", "nonce", "commit"}
    assert "nonce" not in sent["payload"]
    assert reference_commit(sent["payload"], sent["nonce"]) == sent["commit"]


def test_we_cannot_claim_their_verdict_of_us_in_this_dialect():
    """Their submit_audit answers {"ok": true} and keeps the verdict local."""
    bridge, _, _ = _bridge()
    out = bridge.audit({"role": "police", "records": []})
    assert out["verdict"] != VERIFIED_OK
    assert "not reported" in out["verdict"]


# -- cross-dialect audit -----------------------------------------------------
def _ref_record(step, position, nonce="0" * 32):
    payload = {"step": step, "position": list(position)}
    return {"payload": payload, "nonce": nonce,
            "commit": reference_commit(payload, nonce)}


def test_a_clean_reference_log_verifies():
    records = [_ref_record(1, (3, 3)), _ref_record(2, (3, 4))]
    verdict, violations = audit_reference_log(
        records, [r["commit"] for r in records], grid_size=7)
    assert (verdict, violations) == (VERIFIED_OK, [])


def test_a_withheld_step_is_caught_even_though_their_own_audit_would_pass():
    kept, withheld = _ref_record(1, (3, 3)), _ref_record(2, (3, 4))
    verdict, violations = audit_reference_log(
        [kept], [kept["commit"], withheld["commit"]], grid_size=7)
    assert verdict == TAMPERED
    assert any("never revealed" in v for v in violations)


def test_a_rewritten_payload_is_caught():
    record = _ref_record(1, (3, 3))
    record["payload"] = {"step": 1, "position": [0, 0]}
    verdict, violations = audit_reference_log([record], [record["commit"]], grid_size=7)
    assert verdict == TAMPERED
    assert any("hash mismatch" in v for v in violations)


def test_teleporting_between_steps_is_caught():
    records = [_ref_record(1, (0, 0)), _ref_record(2, (6, 6))]
    verdict, violations = audit_reference_log(
        records, [r["commit"] for r in records], grid_size=7)
    assert verdict == TAMPERED
    assert any("jumped" in v for v in violations)


# -- the replay of an interop match ------------------------------------------
def _interop_log():
    mine, my_hash = seal({"kind": "step", "role": "police", "sub_game": 1, "step": 1,
                          "pos_before": [0, 0], "pos_after": [0, 1], "move": "E",
                          "barrier": None, "intent": "truth", "hint": "hi",
                          "scent": []}, REFERENCE)
    theirs = _ref_record(1, (3, 3))
    spec = {"payload": {"step": 0, "type": "system_spec"}, "nonce": "1" * 32}
    spec["commit"] = reference_commit(spec["payload"], spec["nonce"])
    return {"my_records": [mine], "my_hashes": [my_hash],
            "opponent_records": [spec, theirs], "opponent_hashes": [theirs["commit"]],
            "commit_dialect": REFERENCE, "perspective": "police"}


def test_interop_log_replays_as_verified():
    """Regression: their envelope used to be re-hashed as one of ours, which
    flagged a perfectly clean interop match as TAMPERED."""
    verdict, mine, theirs = replay_data.verdict_of(_interop_log())
    assert verdict == VERIFIED_OK
    assert all(mine) and all(theirs)


def test_interop_replay_shows_both_sides():
    steps = replay_data.timeline(_interop_log())
    assert {item["role"] for item in steps} == {"police", "thief"}
    assert all(item["verified"] for item in steps)


def test_interop_replay_catches_a_tampered_opponent_record():
    log = _interop_log()
    log["opponent_records"][1]["payload"] = {"step": 1, "position": [9, 9]}
    verdict, _mine, theirs = replay_data.verdict_of(log)
    assert verdict == TAMPERED
    assert theirs[1] is False


# -- result honesty ----------------------------------------------------------
def test_mutual_agreement_needs_both_directions():
    both = [{"audit": VERIFIED_OK, "opponent_audit": VERIFIED_OK}]
    one_way = [{"audit": VERIFIED_OK, "opponent_audit": "not reported"}]
    assert results.agreement_reached(both) is True
    assert results.agreement_reached(one_way) is False
    assert results.agreement_reached([]) is False


def test_a_win_claim_is_sent_immediately_not_carried_to_a_turn_that_never_comes():
    """Measured live 2026-08-01. A win claim is terminal - the sub-game is over,
    so there is no next turn to ride. Left owed, their peer waits out its turn
    timeout, and `timeout` is in their NO_AUDIT_RESULTS: they skip the audit
    exchange entirely. Every even sub-game came back `audit=no package received`
    with zero opponent records, which is also why cloning got no data from the
    role we play on even sub-games.
    """
    bridge, _service, peer = _bridge()
    bridge.commit({"hash": "c" * 64}, timeout=1)
    bridge.reveal(_reveal(role="thief", step=4, hash="c" * 64), timeout=1)
    sent_before = len(peer.turns)

    bridge.event({"public": {"kind": "survival"}}, timeout=1)

    assert len(peer.turns) == sent_before + 1, "the claim must go out on its own"
    final = peer.turns[-1]
    assert final["win_claim"] == {"type": "survival"}
    assert final["step"] == 4 and final["commit"] == "c" * 64, "a copy of our last turn"
    assert bridge._owed_win_claim is None, "nothing is left owed"


def test_a_claim_answer_still_rides_the_next_turn():
    """The capture answer is NOT terminal - the game continues - so it keeps the
    original behaviour and must not be pushed as a message of its own."""
    from p2p_pursuit.domain.protocol import KIND_CAPTURE_ANSWER

    bridge, _service, peer = _bridge()
    bridge.commit({"hash": "d" * 64}, timeout=1)
    bridge.reveal(_reveal(role="thief", step=4, hash="d" * 64), timeout=1)
    sent_before = len(peer.turns)
    bridge.event({"public": {"kind": KIND_CAPTURE_ANSWER, "claim_cell": [1, 2],
                             "answer": False}}, timeout=1)
    assert len(peer.turns) == sent_before, "it waits for the next turn"
    assert bridge._owed_claim_response == {"claim": [1, 2], "caught": False}


def test_an_inbound_agreement_counts_as_liveness():
    """Over a tunnel each failed liveness probe costs its full timeout, so sixty
    of them take minutes - while a reference peer allows only ~60 s for our
    answer before exiting with "Opponent never sent its agreement" (measured
    2026-08-01 over two Cloudflare tunnels, both peers alive, neither able to
    start). An agreement already in our inbox proves they reached us, which is
    stronger evidence than any probe of ours.
    """
    bridge, _service, _peer = _bridge()
    assert bridge.opponent_already_contacted() is False
    bridge.on_negotiate({"terms": {}, "nonce": "n", "signature": "s", "identity": {}})
    assert bridge.opponent_already_contacted() is True
