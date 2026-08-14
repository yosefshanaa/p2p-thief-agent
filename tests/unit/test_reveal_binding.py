"""Every commitment sent in play is revealed - as the same bytes, under its own index.

The defect these pin was found by amireman auditing our AHK-DEMO3 reveal: of the
14 commitments we sent during their sub-game 5, *none* appeared in the records
we revealed for it, and the package they filed for sub-game 6 held 15 records
instead of 35 - one of them binding to a commitment from sub-game 5. Every
record still verified against its own hash. It was never a hashing failure: our
package named no sub-game, so it could only be filed by arrival time, and our
peer waits for their reveal before advancing while theirs does not. Their index
had moved on by the time ours landed, and under role alternation that also
inverts every role label in the package.
"""

from __future__ import annotations

from p2p_pursuit.domain.crypto import REFERENCE, reference_commit
from p2p_pursuit.domain.protocol import record_sub_game
from p2p_pursuit.infra import interop_codec as codec
from p2p_pursuit.infra.interop_audit import verify_outgoing_reveal
from p2p_pursuit.peer import audit_bridge
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from tests.conftest import make_peer, make_shared


def _pair(dialect: str = REFERENCE):
    shared = make_shared(**{"movement_and_barriers.max_moves": 8,
                            "movement_and_barriers.survival_threshold": 8})
    police = TurnEngine("police", shared, make_peer("police", interop_dialect=dialect), seed=1)
    thief = TurnEngine("thief", shared, make_peer("thief", interop_dialect=dialect), seed=2)
    return police, thief


def _play(police, thief, n):
    police.begin_sub_game(n)
    thief.begin_sub_game(n)
    play_sub_game(police, thief)


# -- the package belongs to its own sub-game ---------------------------------
def test_the_reveal_for_a_finished_sub_game_survives_the_next_one_starting():
    """The regression. Sub-game 2 starting must not empty sub-game 1's package."""
    police, thief = _pair()
    _play(police, thief, 1)
    first = audit_bridge.audit_package(thief, 1)
    _play(police, thief, 2)

    late = audit_bridge.audit_package(thief, 1)
    assert late["records"] == first["records"], "the frozen reveal must not drift"
    assert late["hashes"] == first["hashes"]
    assert late["sub_game"] == late["sub_game_number"] == 1
    assert late["records"], "sub-game 1's records must still be there after 2 began"
    assert audit_bridge.audit_package(thief, 2)["records"] != first["records"]


def test_the_role_frozen_into_the_package_is_the_role_that_played_it():
    """Under alternation a late package read against the wrong index reads as a
    role inversion - so the package states the role it was played with."""
    police, thief = _pair()
    _play(police, thief, 1)
    package = audit_bridge.audit_package(thief, 1)
    thief.set_role("police")  # the swap the next sub-game owes
    thief.begin_sub_game(2)
    assert audit_bridge.audit_package(thief, 1)["role"] == package["role"] == "thief"


def test_a_reveal_carries_no_other_sub_games_records():
    police, thief = _pair()
    for n in (1, 2, 3):
        _play(police, thief, n)
    for n in (1, 2, 3):
        package = audit_bridge.audit_package(thief, n)
        assert package["records"]
        assert {record_sub_game(r) for r in package["records"]} == {n}


def test_every_record_carries_the_index_in_both_spellings():
    """Ours says `sub_game`, the reference family says `sub_game_number`. A peer
    bucketing our reveal by content must not have to know which."""
    police, thief = _pair()
    _play(police, thief, 1)
    for record in audit_bridge.audit_package(thief, 1)["records"]:
        assert record["sub_game"] == record["sub_game_number"] == 1


# -- the reveal binds to what went on the wire -------------------------------
def test_the_revealed_commit_is_the_one_we_sent_live_not_a_fresh_derivation():
    police, thief = _pair()
    _play(police, thief, 1)
    package = audit_bridge.audit_package(thief, 1)
    envelope = codec.reference_records(package["records"], package["hashes"])

    assert [record["commit"] for record in envelope] == package["hashes"]
    for record in envelope:
        assert reference_commit(record["payload"], record["nonce"]) == record["commit"]


def test_a_payload_that_drifted_after_sealing_reveals_the_live_commitment():
    """The failure mode that hides itself: re-deriving the commit at audit time
    makes a package that binds to nothing still pass its own verification."""
    police, thief = _pair()
    _play(police, thief, 1)
    package = audit_bridge.audit_package(thief, 1)
    drifted = [dict(package["records"][0], hint="edited after the commitment"),
               *package["records"][1:]]

    envelope = codec.reference_records(drifted, package["hashes"])
    assert envelope[0]["commit"] == package["hashes"][0], "the live commitment is revealed"
    violations = verify_outgoing_reveal(envelope, package["hashes"],
                                        sub_game=1, role=package["role"])
    assert violations and "not to its own commitment" in violations[0]


def test_the_self_check_passes_on_an_honest_reveal():
    police, thief = _pair()
    _play(police, thief, 1)
    for engine in (police, thief):
        package = audit_bridge.audit_package(engine, 1)
        envelope = codec.reference_records(package["records"], package["hashes"])
        assert verify_outgoing_reveal(envelope, package["hashes"],
                                      sub_game=1, role=package["role"]) == []


def test_a_withheld_commitment_is_caught_by_our_own_self_check():
    police, thief = _pair()
    _play(police, thief, 1)
    package = audit_bridge.audit_package(thief, 1)
    envelope = codec.reference_records(package["records"], package["hashes"])

    violations = verify_outgoing_reveal(envelope[:-1], package["hashes"],
                                        sub_game=1, role=package["role"])
    assert any("sent in play and is not revealed" in v for v in violations)


def test_a_reveal_that_lands_after_the_receiver_moved_on_is_still_filed_right():
    """AHK-DEMO3, from the other chair.

    Our peer waits up to 20 s for their reveal before advancing; a peer that
    does not wait is already on sub-game 6 when our sub-game 5 package lands.
    Filed by arrival that package binds to nothing and - under alternation -
    reads as a role inversion. Filed by the index it names, it verifies.
    """
    from p2p_pursuit.infra.interop_bridge import ReferenceBridge
    from p2p_pursuit.peer.service import PeerService

    police, thief = _pair()
    for n in (4, 5):
        _play(police, thief, n)

    sender = ReferenceBridge(PeerService(thief, {}), _RecordingPeer(),
                             grid_size=7, terms={}, identity={})
    sender.audit(audit_bridge.audit_package(thief, 5))
    envelope = sender.link.audits[0]
    assert envelope["sub_game"] == 5

    police.begin_sub_game(6)  # they crossed the boundary before our package landed
    receiver_service = PeerService(police, {})
    receiver = ReferenceBridge(receiver_service, _RecordingPeer(),
                               grid_size=7, terms={}, identity={})
    receiver.on_submit_audit(envelope)

    assert 6 not in receiver_service.audit_packages, "not the sub-game we are on"
    assert receiver_service.audit_verdicts[5]["verdict"] == "Verified OK"
    assert receiver_service.audit_verdicts[5]["violations"] == []


class _RecordingPeer:
    def __init__(self):
        self.audits: list[dict] = []

    def submit_audit(self, payload, timeout=None):
        self.audits.append(payload)
        return {"ok": True}


def test_a_reveal_holding_a_neighbouring_sub_games_record_is_caught():
    police, thief = _pair()
    _play(police, thief, 1)
    first = audit_bridge.audit_package(thief, 1)
    _play(police, thief, 2)
    second = audit_bridge.audit_package(thief, 2)

    mixed = codec.reference_records(
        [*second["records"], first["records"][0]],
        [*second["hashes"], first["hashes"][0]])
    violations = verify_outgoing_reveal(mixed, second["hashes"],
                                        sub_game=2, role=second["role"])
    assert any("belongs to sub-game 1, not 2" in v for v in violations)
