"""yanell11's contract: the first lock we bound by adopting *their* document.

Every previous pairing settled the scent lock by finding a document we both
already held. This one could not: their `multiplicative_book_v1` is pinned
byte-for-byte in their own vendored conformance vectors, so they cannot relabel
it, and `check_compatibility` refuses on a hash difference, so we cannot ignore
it. The physics turned out to be *identical* to our `registered_v3` - same
kernel, same rho, same clamp, same one-expression update, same serve-after-
update - which is the whole lesson: **the lock is over the document and never
over the behaviour**, and two teams running provably the same physics still
refuse each other until one adopts the other's bytes.

So we now hold both documents for one physics and declare whichever a given
opponent is pinned to. The registration is therefore document-only; the two
models must stay behaviourally indistinguishable, which is what
`test_the_new_model_is_the_registered_physics` pins.

The uid change has the same shape. Their labelled derivation is pinned by their
unit tests as a collision fix - two labelled series between the same two teams
otherwise share a uid, because a label reaches the `game_id` and never the
`game_uid`. We adopted it behind a defaulted argument so that the unlabelled
seed stays byte-identical, which is what every peer we have already played
agreed with us; `test_the_unlabelled_seed_did_not_move` is that guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path

from p2p_pursuit.domain.crypto import reference_commit, sha256_hex, spaced_bytes
from p2p_pursuit.domain.game_ids import reference_game_id, reference_game_uid
from p2p_pursuit.domain.negotiation import scent_model_sha256
from p2p_pursuit.domain.scent import (
    MULTIPLICATIVE_BOOK_V1,
    REGISTERED_MODELS,
    REGISTERED_V3,
    ScentField,
    scent_model_document,
)
from p2p_pursuit.domain.scent_locate import SERVES_AFTER_EMISSION, fix_lag
from p2p_pursuit.infra.interop_codec import interop_terms
from p2p_pursuit.report.mutual_signature import mutual_signature
from p2p_pursuit.shared.config import load_shared

#: Their §B, and the value their vendored vectors pin. We hold their bytes.
THEIR_SCENT_LOCK = "934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9"
#: Their two published golden vectors (2026-08-23).
THEIR_COMMIT_VECTOR = "957ef2bece857ea964cc519a844c229235c8f9deddefd33061204b09be4071c7"
THEIR_RESULT_VECTOR = "f0f83af87f15ca5bd3584c3ffca167a94e0e4e7c91665d3b4f3e451746e93a75"
#: The agreed series label and the two uids it separates.
LABELLED_GAME_ID = "ahk-yosi-vs-yanell11-friendly-1"
LABELLED_UID = "a0b99406-11d1-384c-823c-0315c9596bab"
UNLABELLED_UID = "9bb658ea-115b-ba62-e722-231e85ab340b"
LOCK_FILE = Path("docs/locks/scent_multiplicative_book_v1.json")


def haifa_terms() -> dict:
    """The 14 signed terms under the setting we agreed with them."""
    shared = load_shared(Path("config/police/game.json"))
    return {**interop_terms(shared, num_games=None), "setting": "Haifa"}


def test_their_document_is_the_one_we_now_declare() -> None:
    assert scent_model_sha256(MULTIPLICATIVE_BOOK_V1) == THEIR_SCENT_LOCK


def test_the_lock_file_is_its_own_wire_value() -> None:
    """Canonical bytes, no trailing newline - so `sha256sum` alone verifies it.

    An opponent must be able to check the document we publish without running
    any of our code, which is exactly how we asked them to check ours.
    """
    raw = LOCK_FILE.read_bytes()
    assert not raw.endswith(b"\n"), "a trailing newline breaks the file's own digest"
    assert sha256_hex(raw) == THEIR_SCENT_LOCK
    assert json.loads(raw) == scent_model_document(MULTIPLICATIVE_BOOK_V1)


def test_the_new_model_is_the_registered_physics_exactly() -> None:
    """Document-only registration: same served field as `registered_v3`, always.

    If these two ever diverge the registration has stopped being a relabelling
    and has become a second physics nobody measured a doctrine against.
    """
    assert MULTIPLICATIVE_BOOK_V1 in REGISTERED_MODELS
    theirs, ours = ScentField(7, model=MULTIPLICATIVE_BOOK_V1), ScentField(7, model=REGISTERED_V3)
    for cell in ((3, 3), (3, 4), (4, 4), (4, 3), (3, 3)):
        assert theirs.serve_for_step(cell) == ours.serve_for_step(cell)


def test_the_documents_differ_even_though_the_physics_does_not() -> None:
    """The reason this model exists at all - state it, so nobody 'tidies' it away."""
    assert scent_model_sha256(MULTIPLICATIVE_BOOK_V1) != scent_model_sha256(REGISTERED_V3)


def test_the_new_model_serves_after_its_own_emission() -> None:
    """The trap: a registered model missing here reads the opponent a step stale.

    `fix_lag` is what turns two served fields into "where they stand now"; a
    model that serves post-emission but is absent from the set is silently given
    `book_v1`'s one-step lag, and the error never surfaces as an exception.
    """
    assert MULTIPLICATIVE_BOOK_V1 in SERVES_AFTER_EMISSION
    assert fix_lag(MULTIPLICATIVE_BOOK_V1) == 0


def test_their_peak_deposit_field_is_what_we_serve() -> None:
    """Their §4: freshest centre 0.9, clamped - the numbers we sent them to diff."""
    served = ScentField(7, model=MULTIPLICATIVE_BOOK_V1).serve_for_step((3, 3))
    assert served[3][3] == 0.9          # centre, at the clamp
    assert served[3][4] == 0.62         # orthogonal
    assert served[2][2] == 0.42         # diagonal
    assert served[3][5] == 0.20         # ring 2


def test_their_clamp_example_reproduces() -> None:
    """Their document carries the saturating case, including the IEEE-754 tail."""
    example = scent_model_document(MULTIPLICATIVE_BOOK_V1)["example"]
    raw = (1 - 0.1) * example["tau"] + example["delta"]
    assert raw == example["raw"] == 1.4300000000000002
    assert min(0.9, max(0.0, raw)) == example["clamped"]


def test_our_terms_are_byte_identical_to_theirs_under_haifa() -> None:
    """Exactly one key separated the two contracts, and it is a negotiated one."""
    theirs = ('{"axis_origin_corner":"top-left","axis_start_index":0,"barriers_max":14,'
              '"board_size":7,"cop_start":[0,0],"decay_per_step":0.1,"emit_intensity":0.9,'
              '"hint_max_words":15,"max_steps":35,"min_center_intensity":0.5,"num_games":6,'
              '"setting":"Haifa","smell_grid_size":5,"thief_start":[3,3]}')
    assert json.dumps(haifa_terms(), sort_keys=True, separators=(",", ":")) == theirs


def test_the_label_reaches_the_uid() -> None:
    """Their collision fix: two labelled series must not share one uid."""
    terms = haifa_terms()
    assert reference_game_id("ahk-yosi", "yanell11") == "ahk-yosi-vs-yanell11"
    assert reference_game_uid(terms, "ahk-yosi", "yanell11",
                              game_id=LABELLED_GAME_ID) == LABELLED_UID
    counted = reference_game_uid(terms, "ahk-yosi", "yanell11",
                                 game_id="ahk-yosi-vs-yanell11-counted-1")
    assert counted != LABELLED_UID, "friendly and counted collided - the bug this fixes"


def test_the_unlabelled_seed_did_not_move() -> None:
    """The regression guard for every opponent we have already played.

    Their labelled rule is an addition, not a replacement: with no label the
    material is still `canonical(terms) | lo | hi`, so a peer that agreed a uid
    with us last month still derives the same one.
    """
    terms = haifa_terms()
    assert reference_game_uid(terms, "ahk-yosi", "yanell11") == UNLABELLED_UID
    assert reference_game_uid(terms, "yanell11", "ahk-yosi") == UNLABELLED_UID
    assert reference_game_uid(terms, "ahk-yosi", "yanell11", game_id="") == UNLABELLED_UID
    assert UNLABELLED_UID != LABELLED_UID


def test_their_commit_vector_reproduces() -> None:
    payload = {"move": "STAY", "position": [0, 0], "role": "police",
               "step": 0, "sub_game": 1}
    assert reference_commit(payload, "00112233445566778899aabbccddeeff") == THEIR_COMMIT_VECTOR


def test_their_result_digest_reproduces_through_our_own_signer() -> None:
    """Not a re-implementation of their rule - the function we file with."""
    rows = [{"sub_game_number": n,
             "roles": {"ahk-yosi": "police", "yanell11": "thief"} if n % 2 else
                      {"ahk-yosi": "thief", "yanell11": "police"},
             "result": "capture",
             "winner_group": "ahk-yosi" if n % 2 else "yanell11",
             "score": {"ahk-yosi": 20, "yanell11": 5} if n % 2 else
                      {"ahk-yosi": 5, "yanell11": 20}} for n in range(1, 7)]
    result = {"game_id": LABELLED_GAME_ID,
              "aggregate": {"series_tie": True,
                            "sub_games_won": {"ahk-yosi": 3, "yanell11": 3},
                            "ties": 0,
                            "total_score": {"ahk-yosi": 77, "yanell11": 77},
                            "winner_group": None},
              "sub_games": rows}
    assert mutual_signature(result) == THEIR_RESULT_VECTOR


def test_the_settlement_encoding_is_spaced_not_compact() -> None:
    """The trap both teams named: the compact form is wrong-but-plausible hex."""
    doc = {"game_id": LABELLED_GAME_ID, "aggregate": {}, "sub_games": []}
    compact = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert spaced_bytes(doc) != compact
