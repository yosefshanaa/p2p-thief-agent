"""Every golden vector published in docs/INTEROP_GUIDE.md, pinned.

That document is sent to other teams and invites them to reproduce these values
before the first move. A published contract that drifts from the code is worse
than no contract: the opponent reproduces our number, we compute a different
one, and neither side can audit the other. So the guide's vectors are asserted
here rather than trusted to stay true.

Deliberately computed with plain `hashlib`/`json`/`uuid` on the left-hand side,
exactly as an opponent would - importing our helpers on both sides would only
prove we are self-consistent.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from p2p_pursuit.domain.crypto import canonical_bytes, reference_commit
from p2p_pursuit.domain.game_ids import reference_game_id, reference_game_uid
from p2p_pursuit.report.consensus import consensus_sha

NONCE = "ab" * 16

#: §4 of the guide. Values AND JSON types - a float that becomes an int refuses
#: every handshake in the reference family, whose verify_peer compares by equality.
TERMS = {
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "barriers_max": 14,
    "board_size": 7,
    "cop_start": [0, 0],
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "hint_max_words": 15,
    "max_steps": 35,
    "min_center_intensity": 0.5,
    "num_games": 6,
    "setting": "New York",
    "smell_grid_size": 5,
    "thief_start": [3, 3],
}

STEP_RECORD = {
    "kind": "step", "role": "thief", "sub_game": 1, "sub_game_number": 1, "step": 1,
    "pos_before": [3, 3], "pos_after": [3, 4], "move": "E", "barrier": None,
    "intent": "lie", "hint": "north side", "scent": [[0.0, 0.0], [0.0, 0.81]],
}


def _canon(obj) -> bytes:
    """Canonical JSON as the guide specifies it, written out longhand."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def test_canonical_json_is_what_the_guide_says_it_is():
    assert _canon(STEP_RECORD) == canonical_bytes(STEP_RECORD)
    assert _canon(STEP_RECORD).decode() == (
        '{"barrier":null,"hint":"north side","intent":"lie","kind":"step","move":"E",'
        '"pos_after":[3,4],"pos_before":[3,3],"role":"thief",'
        '"scent":[[0.0,0.0],[0.0,0.81]],"step":1,"sub_game":1,"sub_game_number":1}')


def test_the_trivial_commit_golden_vector():
    expected = "2d5faf71c42626d681a5727c2e7940af4c8e21e7f59f3acd6e063ae654bcee0a"
    assert reference_commit({"a": 1}, NONCE) == expected
    assert hashlib.sha256(_canon({"a": 1}) + b"|" + NONCE.encode()).hexdigest() == expected


def test_the_step_record_commit_golden_vector():
    expected = "a963512dd17cb3b86f6fe1d9027d1b03de14cdbd791f4c809d98e8b4ff9836a0"
    assert reference_commit(STEP_RECORD, NONCE) == expected
    assert hashlib.sha256(_canon(STEP_RECORD) + b"|" + NONCE.encode()).hexdigest() == expected


def test_the_game_id_and_uid_golden_vectors():
    """Derived from the terms and both slugs, so both peers reach them alone."""
    assert reference_game_id("ahk-yosi", "amireman") == "ahk-yosi-vs-amireman"
    assert reference_game_uid(TERMS, "ahk-yosi", "amireman") == \
        "4cada35c-bba4-72c7-0838-d6fd723e13b8"
    assert reference_game_uid(TERMS, "ahk-yosi", "uoh-sqak") == \
        "52d2d904-28d5-50f0-54d3-5842ad94f198"


def test_the_uid_derivation_longhand_agrees():
    lo, hi = sorted(("ahk-yosi", "amireman"))
    material = _canon(TERMS) + b"|" + lo.encode() + b"|" + hi.encode()
    longhand = str(uuid.UUID(bytes=hashlib.sha256(material).digest()[:16]))
    assert longhand == reference_game_uid(TERMS, "ahk-yosi", "amireman")


def test_the_consensus_digest_golden_vector():
    document = {
        "game_id": "a-vs-b", "game_uid": "uid-1234",
        "sub_games": [
            {"result": "survival", "roles": {"ahk-yosi": "police", "them": "thief"},
             "score": {"ahk-yosi": 5, "them": 10}, "sub_game_number": 1,
             "winner_group": "them"},
            {"result": "capture", "roles": {"ahk-yosi": "thief", "them": "police"},
             "score": {"ahk-yosi": 5, "them": 20}, "sub_game_number": 2,
             "winner_group": "them"},
        ],
    }
    expected = "3d2eddb4692b0a42fa3b01a37ad9241f40734687730be4f74724c5b115443764"
    assert consensus_sha(document) == expected
    assert hashlib.sha256(_canon(document)).hexdigest() == expected


def test_the_published_terms_are_the_ones_we_actually_send():
    """The guide's 14 terms must be what interop_codec emits for the committed
    constitution - a guide describing a config we no longer load is a trap."""
    from pathlib import Path

    from p2p_pursuit.infra.interop_codec import interop_terms
    from p2p_pursuit.shared.config import load_role

    base = Path(__file__).resolve().parents[2]
    shared, _peer = load_role(base / "config" / "police")
    assert interop_terms(shared) == TERMS


def test_the_published_constitution_hash_is_current():
    """The guide's number must be the one our committed file actually produces.

    Read out of the guide rather than hardcoded here, because this digest is
    **per-pairing**: `agreed_between` names both teams and is inside the hashed
    object, so it changes every time we name a new opponent. A third copy of the
    value in the test suite would mean every pairing starts by editing a test,
    which trains exactly the wrong reflex. What is invariant is that the guide
    and the file agree - so that is what is asserted.
    """
    import re
    from pathlib import Path

    from p2p_pursuit.domain.crypto import digest

    base = Path(__file__).resolve().parents[2]
    guide = (base / "docs" / "INTEROP_GUIDE.md").read_text(encoding="utf-8")
    published = re.search(r"^([0-9a-f]{64})$", guide, re.MULTILINE)
    assert published, "the guide no longer publishes a constitution hash"
    raw = json.loads((base / "config" / "police" / "game.json").read_text())
    assert digest(raw) == published.group(1), (
        "docs/INTEROP_GUIDE.md quotes a stale constitution hash - it moves with "
        "`agreed_between`, so re-publish it whenever the pairing changes")


def test_the_two_role_constitutions_stay_byte_identical():
    """Whatever the pairing, both roles must load the same file (book 9.4)."""
    from pathlib import Path

    base = Path(__file__).resolve().parents[2] / "config"
    assert (base / "police" / "game.json").read_bytes() == \
        (base / "thief" / "game.json").read_bytes()
