"""The reference-dialect bridge, driven by a stand-in for their peer.

Every shape here was taken from the reference implementation's own source and
confirmed against it in a live warm-up match (RUNBOOK 3b): our peer played a
full sub-game against an unmodified reference peer, its audit returned
``log_verified: true`` on our records, and ours returned ``Verified OK`` on
theirs. These tests keep that interoperability from regressing silently.
"""

from __future__ import annotations

from p2p_pursuit.domain.audit import NOT_REPORTED_REFERENCE, TAMPERED, VERIFIED_OK
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
        self.commit_dialect = REFERENCE
        self.audit_ledger: dict = {}

    def declare_technical(self, offender, reason):
        self.technical.append((offender, reason))

    def opponent_hashes_for(self, n):
        return list(self.opp_hashes) if n == self.sub_game else []

    def audit_snapshot(self, n=None):
        n = self.sub_game if n is None else n
        return {"sub_game": n, "role": self.role, "records": [], "hashes": [],
                "opp_hashes": []}


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


def _surviving_thief_engine():
    """A thief whose 35th step has just ended the sub-game by survival.

    `next_package` seals the survival claim while it builds the same package as
    the reveal, so the engine is already finished when the bridge is asked to
    send that turn - which is what lets the claim ride the first send.
    """
    import types

    engine = _FakeEngine(role="thief")
    engine.my_steps = 35
    engine.shared = types.SimpleNamespace(survival_threshold=35)
    engine.end = types.SimpleNamespace(ending="survival", winner="thief",
                                       cause="survived 35 steps")
    return engine


def test_survival_rides_the_step_that_earns_it_not_a_second_copy():
    """Regression, measured live vs s82kma9e 2026-08-17.

    Their inbox keys on (step, commit) and absorbs a later message carrying the
    same pair as an HTTP redelivery. We used to send step 35 bare and then
    restate it with `win_claim` attached, so the declaration was never
    adjudicated: their police waited its full 180 s turn deadline over a
    survival we had already declared, and the resulting drift voided three
    sub-games. The claim must be on the first and only send of that step.
    """
    engine = _surviving_thief_engine()
    bridge, _, peer = _bridge(service=_FakeService(engine))

    bridge.commit({"hash": "b" * 64})
    bridge.reveal(_reveal(role="thief", step=35))

    assert len(peer.turns) == 1, "the step that ends the sub-game is sent once"
    assert peer.turns[0]["win_claim"] == {"type": "survival"}
    assert peer.turns[0]["step"] == 35

    # The engine's survival event arrives next in the very same package. It has
    # nothing left to deliver, and must not restate an already-delivered step.
    bridge.event({"public": {"kind": "survival_claim"}})
    assert len(peer.turns) == 1, "no duplicate step 35 for their inbox to absorb"


def test_a_mid_game_thief_turn_carries_no_win_claim():
    """The guard is the finished sub-game, not the role: an unfinished thief
    turn must stay bare, or every step would declare victory."""
    import types

    engine = _FakeEngine(role="thief")
    engine.my_steps, engine.end = 12, None
    engine.shared = types.SimpleNamespace(survival_threshold=35)
    bridge, _, peer = _bridge(service=_FakeService(engine))

    bridge.commit({"hash": "b" * 64})
    bridge.reveal(_reveal(role="thief", step=12))
    assert peer.turns[0]["win_claim"] is None


def test_a_captured_thief_does_not_announce_survival():
    """Reaching the step count and *being caught* on it are different endings;
    only the survival ending may ride as a survival win claim."""
    import types

    engine = _FakeEngine(role="thief")
    engine.my_steps = 35
    engine.shared = types.SimpleNamespace(survival_threshold=35)
    engine.end = types.SimpleNamespace(ending="capture", winner="police",
                                       cause="landed on the thief")
    bridge, _, peer = _bridge(service=_FakeService(engine))

    bridge.commit({"hash": "b" * 64})
    bridge.reveal(_reveal(role="thief", step=35))
    assert peer.turns[0]["win_claim"] is None


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
    sealed, commit = seal({"kind": "step", "step": 1}, REFERENCE)
    bridge.audit({"role": "police", "records": [sealed], "hashes": [commit]})
    # records[0] is the step-0 system spec; ours is what follows it.
    sent = peer.audits[0]["records"][1]
    assert set(sent) == {"payload", "nonce", "commit"}
    assert "nonce" not in sent["payload"]
    assert reference_commit(sent["payload"], sent["nonce"]) == sent["commit"]


def test_our_audit_envelope_names_the_sub_game_it_is_for():
    """A package that names no index can only be filed by arrival time, and the
    two peers do not cross a boundary together - which is how our sub-game 5
    reveal was audited against amireman's sub-game 6."""
    bridge, _, peer = _bridge()
    sealed, commit = seal({"kind": "step", "step": 1, "sub_game": 5}, REFERENCE)
    bridge.audit({"role": "thief", "sub_game": 5, "records": [sealed],
                  "hashes": [commit]})
    envelope = peer.audits[0]
    assert envelope["sub_game"] == envelope["sub_game_number"] == 5


def test_the_revealed_commit_is_the_live_one_not_a_fresh_derivation():
    bridge, _, peer = _bridge()
    sealed, commit = seal({"kind": "step", "step": 1, "sub_game": 1}, REFERENCE)
    bridge.audit({"role": "police", "sub_game": 1, "records": [sealed],
                  "hashes": [commit]})
    revealed = peer.audits[0]["records"][-1]
    assert revealed["commit"] == commit
    assert reference_commit(revealed["payload"], revealed["nonce"]) == commit


def test_the_step_0_system_spec_is_sealed_once_not_reminted_per_call():
    """`submit_audit` is retried on a flaky link. A record resealed per attempt
    reveals one claim under two commitments - a nonce generated at audit time."""
    bridge, _, peer = _bridge()
    package = {"role": "police", "sub_game": 1, "records": [], "hashes": []}
    bridge.audit(package)
    bridge.audit(package)
    first, second = (audit["records"][0] for audit in peer.audits)
    assert first["payload"]["type"] == "system_spec"
    assert (first["nonce"], first["commit"]) == (second["nonce"], second["commit"])


def test_a_reveal_that_does_not_bind_is_caught_before_it_is_sent():
    """Both halves of the check the opponent asked us to run locally: a payload
    that no longer hashes to its commitment, and a commitment with no record."""
    bridge, _, _ = _bridge()
    sealed, commit = seal({"kind": "step", "step": 1, "sub_game": 1}, REFERENCE)

    bridge.audit({"role": "police", "sub_game": 1, "records": [sealed],
                  "hashes": ["f" * 64]})
    assert any("not to its own commitment" in v for v in bridge.reveal_self_checks[1])

    bridge.audit({"role": "police", "sub_game": 2, "records": [sealed],
                  "hashes": [commit, "e" * 64]})
    assert any("sent in play and is not revealed" in v
               for v in bridge.reveal_self_checks[2])


def test_their_reveal_is_filed_by_the_sub_game_it_names_not_by_when_it_lands():
    engine = _FakeEngine()
    engine.sub_game = 6  # we have moved on; their package is for the one before
    engine.audit_ledger[5] = {"sub_game": 5, "role": "thief", "records": [],
                              "hashes": [], "opp_hashes": []}
    bridge, service, _ = _bridge(service=_FakeService(engine))
    bridge.on_submit_audit({"sender": "thief", "sub_game": 5, "records": []})
    assert 5 in service.audit_packages and 6 not in service.audit_packages


def test_their_reveal_is_filed_by_its_records_when_the_envelope_is_silent():
    engine = _FakeEngine()
    engine.sub_game = 6
    engine.audit_ledger[5] = {"sub_game": 5, "role": "thief", "records": [],
                              "hashes": [], "opp_hashes": []}
    bridge, service, _ = _bridge(service=_FakeService(engine))
    payload = {"step": 1, "position": [3, 3], "sub_game_number": 5}
    nonce = "0" * 32
    bridge.on_submit_audit({"sender": "thief", "records": [
        {"payload": payload, "nonce": nonce,
         "commit": reference_commit(payload, nonce)}]})
    assert 5 in service.audit_packages


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


def test_the_reference_dialects_own_blindness_does_not_block_agreement():
    """Neither reference peer can answer with a verdict, so requiring one made
    this flag unreachable - and filed `false` against najamjad's `true` on a
    6-0 series that both sides audited clean. Contradicting signed reports is
    what rule 35 voids for, so the sentinel for "the wire cannot carry it" is
    non-blocking while every other non-verdict stays blocking.
    """
    blind = [{"audit": VERIFIED_OK, "opponent_audit": NOT_REPORTED_REFERENCE}]
    assert results.agreement_reached(blind) is True


def test_silence_is_still_not_agreement():
    """The distinction the whole change rests on: a peer that went quiet has
    told us nothing, and is not the same as a dialect that cannot speak.
    """
    for verdict in ("not received", "no package received", TAMPERED, ""):
        rows = [{"audit": VERIFIED_OK, "opponent_audit": verdict}]
        assert results.agreement_reached(rows) is False, verdict


def test_our_own_verdict_is_never_waived():
    """Their blindness excuses their half, never ours."""
    rows = [{"audit": TAMPERED, "opponent_audit": NOT_REPORTED_REFERENCE}]
    assert results.agreement_reached(rows) is False


def test_one_bad_window_sinks_the_series():
    rows = [{"audit": VERIFIED_OK, "opponent_audit": NOT_REPORTED_REFERENCE},
            {"audit": VERIFIED_OK, "opponent_audit": "not received"},
            {"audit": VERIFIED_OK, "opponent_audit": NOT_REPORTED_REFERENCE}]
    assert results.agreement_reached(rows) is False


def test_the_bridge_returns_the_exact_sentinel_the_reader_allows():
    """Producer and reader compare strings across two modules; a literal in
    either would let them drift silently into an unreachable flag again.
    """
    import inspect

    from p2p_pursuit.infra import interop_bridge

    source = inspect.getsource(interop_bridge.ReferenceBridge.audit)
    assert "NOT_REPORTED_REFERENCE" in source
    assert '"not reported (reference dialect)"' not in source


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
    """A capture answer of `false` is not terminal - the game continues - so it
    keeps the original behaviour and must not be pushed as a message of its own.

    Scoped deliberately to `false`. The `true` case is terminal and is covered by
    the test below; conflating the two is exactly the assumption that cost three
    sub-games in F001.
    """
    from p2p_pursuit.domain.protocol import KIND_CAPTURE_ANSWER

    bridge, _service, peer = _bridge()
    bridge.commit({"hash": "d" * 64}, timeout=1)
    bridge.reveal(_reveal(role="thief", step=4, hash="d" * 64), timeout=1)
    sent_before = len(peer.turns)
    bridge.event({"public": {"kind": KIND_CAPTURE_ANSWER, "claim_cell": [1, 2],
                             "answer": False}}, timeout=1)
    assert len(peer.turns) == sent_before, "it waits for the next turn"
    assert bridge._owed_claim_response == {"claim": [1, 2], "caught": False}


def test_a_true_capture_answer_is_sent_immediately_like_a_win_claim():
    """Measured live 2026-08-22 (F001 vs vibecode), who diagnosed it from their
    side. Same shape as the win-claim bug above: `caught: true` IS terminal - the
    sub-game ends on it, so there is no next turn to ride. Left owed, their cop
    waits for the answer turn their protocol calls the settlement, times out, and
    skips the audit. All three of our thief windows came back `audit=no package
    received` with zero opponent records, while our own sealed `capture_answer`
    held the right answer on the right cell the whole time.
    """
    from p2p_pursuit.domain.protocol import KIND_CAPTURE_ANSWER

    bridge, _service, peer = _bridge()
    bridge.commit({"hash": "e" * 64}, timeout=1)
    bridge.reveal(_reveal(role="thief", step=7, hash="e" * 64), timeout=1)
    sent_before = len(peer.turns)

    bridge.event({"public": {"kind": KIND_CAPTURE_ANSWER, "claim_cell": [6, 5],
                             "answer": True}}, timeout=1)

    assert len(peer.turns) == sent_before + 1, "the terminal answer goes out alone"
    final = peer.turns[-1]
    assert final["claim_response"] == {"claim": [6, 5], "caught": True}
    assert final["step"] == 7 and final["commit"] == "e" * 64, "a copy of our last turn"
    assert bridge._owed_claim_response is None, "nothing is left owed"


def test_a_true_capture_answer_is_flushed_from_the_live_inbound_path():
    """The regression F002 was actually lost to, and the reason this test exists
    at the entry point instead of at the handler.

    A claim answer reaches the bridge through `_owe`, never through `event`: the
    engine RETURNS the sealed answer from `_answer_claim` and `on_receive_turn`
    hands it straight to `_owe`. The same terminal-flush fix was first applied to
    `event` alone and proved by a test that called `event` directly - both passed,
    and the wire was untouched. All six of our thief windows across F001 and F002
    came back `audit=no package received`.

    So this drives the real inbound message. If a future change moves the routing
    again, this fails and the `event` test above will not.
    """
    from p2p_pursuit.domain.protocol import KIND_CAPTURE_ANSWER

    engine = _FakeEngine(role="thief")
    service = _FakeService(engine)
    service.reveal_response = {"ok": True, "events": [
        {"public": {"kind": KIND_CAPTURE_ANSWER, "claim_cell": [6, 5],
                    "answer": True}, "hash": "f" * 64}]}
    bridge, _service, peer = _bridge(service=service)

    bridge.commit({"hash": "d" * 64}, timeout=1)
    bridge.reveal(_reveal(role="thief", step=14, hash="d" * 64), timeout=1)
    sent_before = len(peer.turns)

    bridge.on_receive_turn({"step": 14, "sender": "police", "hint": "",
                            "smell_grid": {}, "commit": "c" * 64,
                            "timestamp": "t", "barrier_placed": None,
                            "capture_claim": [6, 5], "claim_response": None,
                            "win_claim": None})

    assert len(peer.turns) == sent_before + 1, (
        "the terminal answer must reach the wire from the inbound path - their "
        "cop waits for it and calls it the settlement")
    assert peer.turns[-1]["claim_response"] == {"claim": [6, 5], "caught": True}
    assert bridge._owed_claim_response is None, "nothing is left owed"


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
