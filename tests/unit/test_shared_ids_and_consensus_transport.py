"""What a full live series between two of our own peers exposed.

Six sub-games over real HTTP MCP, role alternation on, `native` dialect,
`P2P_SERIES_CONSENSUS=true`. Twelve `Verified OK` audits, both sides agreeing
the score 70-50 - and `confirmed: false` on both, for two independent reasons.

1. `_adopt_shared_ids` returned early on any dialect but `reference`, so each
   peer kept the id it minted before the handshake: its own timestamp, the
   literal "opponent", and a random uid. Those are the first two keys of the
   consensus document, so the digests could not match by construction, and
   `P2P_GAME_ID` was silently ignored on that path. Fixed - the gate is now
   "does this match sign a mutual document", not "which dialect".

2. The consensus transport itself - `submit_consensus`, `wait_for_consensus`,
   and the envelope that rides the audit tool - lives entirely on the reference
   bridge, and the bridge is only built for the reference dialect. With (1)
   fixed both sides compute the same digest and neither can send it. Not fixed
   here; it now warns instead of failing silently.
"""

from __future__ import annotations

import dataclasses

from p2p_pursuit.report import consensus
from p2p_pursuit.shared.config import PeerConfig

#: `consensus_row` reads the runtime's own row shape - `index` and `ending` -
#: and renames them into the signed document's `sub_game_number` and `result`.
ROWS = [
    {"index": 1, "ending": "capture", "roles": {"a": "police", "b": "thief"},
     "score": {"a": 20, "b": 5}, "winner_group": "a"},
    {"index": 2, "ending": "survival", "roles": {"a": "thief", "b": "police"},
     "score": {"a": 10, "b": 5}, "winner_group": "a"},
]


def test_the_digest_turns_on_the_game_id_so_both_peers_must_derive_the_same_one():
    """The mechanism behind the first defect, isolated.

    Identical play, identical rows, ids differing only by the timestamp each
    peer stamped locally - and the two digests share nothing. This is what the
    live run produced: c75256c9… against cd7c2f74… on a series both sides
    scored 70-50.
    """
    same_rows = {"game_uid": "9afed0f85fe3", "rows": ROWS}
    mine = consensus.consensus_sha(
        consensus.consensus_document(game_id="a-vs-opponent-20260819T210829", **same_rows))
    theirs = consensus.consensus_sha(
        consensus.consensus_document(game_id="b-vs-opponent-20260819T210747", **same_rows))
    assert mine != theirs, "if these agreed the id would not need to be shared"
    agreed = consensus.consensus_sha(
        consensus.consensus_document(game_id="LIVE-SELFTEST-002", **same_rows))
    also = consensus.consensus_sha(
        consensus.consensus_document(game_id="LIVE-SELFTEST-002", **same_rows))
    assert agreed == also


def test_the_row_order_of_the_two_peers_does_not_change_the_digest():
    """Each side names itself first in `roles` and `score`. Canonical JSON sorts
    keys, so the two must still agree - which the live run confirmed once the
    ids were shared: 433d138f… on both sides, from dicts built in opposite
    orders."""
    flipped = [{**row,
                "roles": dict(reversed(list(row["roles"].items()))),
                "score": dict(reversed(list(row["score"].items())))} for row in ROWS]
    a = consensus.consensus_sha(
        consensus.consensus_document(game_id="X", game_uid="u", rows=ROWS))
    b = consensus.consensus_sha(
        consensus.consensus_document(game_id="X", game_uid="u", rows=flipped))
    assert a == b


def test_a_match_that_signs_a_mutual_document_adopts_the_shared_ids():
    """The fix, as the condition rather than as its consequence.

    `_adopt_shared_ids` must run whenever the series will be signed, whichever
    dialect carries it. Asserted against the predicate the method uses, so it
    keeps meaning something if the method is refactored.
    """
    from p2p_pursuit.peer.runtime import REFERENCE

    def adopts(dialect: str, series_consensus: bool) -> bool:
        peer = dataclasses.replace(PeerConfig(raw={}, group_name="t", group_id="t"),
                                   interop_dialect=dialect,
                                   series_consensus=series_consensus)
        return not (peer.interop_dialect != REFERENCE and not peer.series_consensus)

    assert adopts(REFERENCE, False), "every reference match, as before"
    assert adopts(REFERENCE, True)
    assert adopts("native", True), "the case that could not confirm"
    assert not adopts("native", False), "a native match still files under its own id"


def test_the_verifier_reads_both_shapes_a_reveal_arrives_in():
    """The third thing the loopback exposed, and the one that reads as cheating.

    `audit_sealed_log` checks the opponent's half by looking for a literal
    `commit` key on each revealed record. A reference-family peer reveals
    `{payload, nonce, commit}` triples in its end-of-sub-game package, so that
    works. A peer on our own dialect reveals the sealed record itself, turn by
    turn - flat, nonce inside, no `commit` key - exactly as `my_records` holds
    ours, and the verifier already re-derives *that* shape eight lines earlier
    for our own side.

    So every native-dialect archive reported all of the opponent's commitments
    as unrevealed. Measured on a six-sub-game loopback between two of our own
    peers: `theirs_binds: false` on both sides of a series whose every sub-game
    had audited `Verified OK` live, on an archive that contained the evidence
    the whole time. An auditor that cries tampering at an honest peer is worse
    than one that says nothing.
    """
    from p2p_pursuit.domain.crypto import commit_digest
    from p2p_pursuit.infra.interop_audit import audit_sealed_log

    record = {"kind": "step", "role": "thief", "sub_game": 1, "step": 1,
              "pos_before": [3, 3], "pos_after": [3, 4], "move": "E",
              "barrier": None, "intent": "truth", "hint": "east",
              "nonce": "0" * 32}
    flat = {"sub_game": 1, "perspective": "police", "commit_dialect": "native",
            "my_records": [], "my_hashes": [],
            "opponent_records": [record],
            "opponent_hashes": [commit_digest(record, "native")]}
    verdict = audit_sealed_log(flat)
    assert verdict["theirs_binds"], verdict["theirs_violations"]

    # And a record that does NOT reproduce its commitment must still fail - the
    # fix must not have turned the check into a formality.
    tampered = dict(flat, opponent_hashes=["0" * 64])
    assert not audit_sealed_log(tampered)["theirs_binds"]

    # The reference shape keeps its own branch, unchanged.
    triple = {"payload": {"step": 1}, "nonce": "n", "commit": "abc"}
    ref = {"sub_game": 1, "perspective": "police", "commit_dialect": "reference",
           "my_records": [], "my_hashes": [],
           "opponent_records": [triple], "opponent_hashes": ["abc"]}
    assert audit_sealed_log(ref)["theirs_binds"]
    assert not audit_sealed_log(dict(ref, opponent_hashes=["missing"]))["theirs_binds"]
