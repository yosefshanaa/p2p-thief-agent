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
from pathlib import Path

from p2p_pursuit.report import consensus

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


def test_every_dialect_adopts_the_shared_ids(tmp_path):
    """The fix, exercised through the method rather than restated beside it.

    This test used to re-implement `_adopt_shared_ids`'s gate as a local
    expression and assert against that, which is why it passed for as long as
    the gate was wrong: it asserted `not adopts("native", False)` - a native
    match files under its own id - and the gate and the test agreed with each
    other and not with the peer, whose `mutual_signature` is written into every
    result whatever dialect carried it. So it now drives real runtimes, and all
    four combinations must land on the same derived pair.

    See `tests/unit/test_shared_game_ids.py` for the rest of the rule, including
    what happens when the opponent will not name itself.
    """
    from p2p_pursuit.domain.game_ids import reference_game_id
    from p2p_pursuit.peer.runtime import PeerRuntime

    base = Path(__file__).resolve().parent.parent.parent / "config" / "police"
    derived = set()
    for dialect in ("native", "reference"):
        for consensus_on in (False, True):
            rt = PeerRuntime("police", base, out_dir=tmp_path, seed=1)
            rt.peer = dataclasses.replace(rt.peer, interop_dialect=dialect,
                                          series_consensus=consensus_on)
            rt._adopt_shared_ids({"group_id": "uoh-other"})
            derived.add((rt.game_id, rt.game_uid))
    assert len(derived) == 1, f"the dialect still changes the ids: {derived}"
    assert next(iter(derived))[0] == reference_game_id("ahk-yosi", "uoh-other")


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
