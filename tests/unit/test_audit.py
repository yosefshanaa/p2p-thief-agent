"""The audit engine catches every cheat class; honest logs verify clean."""

import copy

from p2p_pursuit.domain.audit import TAMPERED, VERIFIED_OK
from p2p_pursuit.peer import audit_bridge
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from tests.conftest import make_peer, make_shared


def finished_pair(fast=True):
    shared = make_shared(**({"movement_and_barriers.max_moves": 8,
                             "movement_and_barriers.survival_threshold": 8} if fast else {}))
    police = TurnEngine("police", shared, make_peer("police"), seed=1)
    thief = TurnEngine("thief", shared, make_peer("thief"), seed=2)
    play_sub_game(police, thief)
    return police, thief


def test_honest_game_verifies_both_ways():
    police, thief = finished_pair()
    assert audit_bridge.run_audit(police, audit_bridge.audit_package(thief))[0] == VERIFIED_OK
    assert audit_bridge.run_audit(thief, audit_bridge.audit_package(police))[0] == VERIFIED_OK


def _tamper(package, mutate):
    package = copy.deepcopy(package)
    for record in package["records"]:
        if record["kind"] == "step":
            mutate(record)
            break
    return package


def test_rewritten_move_is_caught():
    police, thief = finished_pair()
    pkg = _tamper(audit_bridge.audit_package(thief),
                  lambda r: r.update(move="N" if r["move"] != "N" else "S"))
    verdict, violations = audit_bridge.run_audit(police, pkg)
    assert verdict == TAMPERED and any("hash mismatch" in x for x in violations)


def test_dropped_record_is_caught():
    police, thief = finished_pair()
    pkg = audit_bridge.audit_package(thief)
    pkg = {**pkg, "records": pkg["records"][:-1]}
    assert audit_bridge.run_audit(police, pkg)[0] == TAMPERED


def test_forged_but_consistent_record_is_caught_by_live_hashes():
    """Re-sealing a whole record (valid nonce+hash) still fails: the live
    commitment we received during play does not contain the forged digest."""
    from p2p_pursuit.domain.crypto import seal

    police, thief = finished_pair()
    pkg = audit_bridge.audit_package(thief)
    pkg = copy.deepcopy(pkg)
    record = dict(pkg["records"][0])
    record.pop("nonce")
    record["hint"] = "totally rewritten history"
    sealed, _h = seal(record)
    pkg["records"][0] = sealed
    assert audit_bridge.run_audit(police, pkg)[0] == TAMPERED


def test_audit_is_arrival_order_independent():
    """Content-addressed pairing: shuffled live arrival order still verifies."""
    police, thief = finished_pair()
    police.opp_hashes = list(reversed(police.opp_hashes))
    police.opp_public = list(reversed(police.opp_public))
    assert audit_bridge.run_audit(police, audit_bridge.audit_package(thief))[0] == VERIFIED_OK


def test_dishonest_capture_answer_is_caught():
    police, thief = finished_pair()
    pkg = copy.deepcopy(audit_bridge.audit_package(thief))
    answers = [r for r in pkg["records"] if r["kind"] == "capture_answer"]
    if not answers:  # force a synthetic dishonest answer against the sealed trajectory
        from p2p_pursuit.domain.crypto import seal
        from p2p_pursuit.domain.protocol import capture_answer_record

        last_step = [r for r in pkg["records"] if r["kind"] == "step"][-1]
        lie = capture_answer_record(role="thief", sub_game=thief.sub_game,
                                    at_step=last_step["step"],
                                    claim_cell=tuple(last_step["pos_after"]), answer=False)
        sealed, h = seal(lie)
        pkg["records"].append(sealed)
        police.opp_hashes.append(h)
        police.opp_public.append(None)
    else:
        for a in answers:
            a["answer"] = not a["answer"]
    verdict, violations = audit_bridge.run_audit(police, pkg)
    assert verdict == TAMPERED
