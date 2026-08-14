"""Conformance to the reference family's published wire contract.

These pin the three places where a plausible-but-wrong value is indistinguishable
from a correct one until a real opponent disagrees: the commitment digest, the
deterministic ids, and the mutual result signature's *second* JSON encoding.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from p2p_pursuit.domain.crypto import (
    canonical_bytes,
    reference_commit,
    sha256_raw,
    spaced_bytes,
)
from p2p_pursuit.domain.game_ids import reference_game_id, reference_game_uid
from p2p_pursuit.report.mutual_signature import (
    mutual_signature,
    signature_document,
    signed_aggregate,
    signed_row_fields,
)

TERMS = {"board_size": 7, "max_steps": 35, "setting": "7x7"}


def test_commit_matches_their_published_golden_vector() -> None:
    """Their §4: payload={"a":1}, nonce="ab"*16 -> sha256('{"a":1}|' + "ab"*16)."""
    nonce = "ab" * 16
    expected = hashlib.sha256(('{"a":1}|' + nonce).encode("utf-8")).hexdigest()
    assert reference_commit({"a": 1}, nonce) == expected


def test_commit_uses_compact_separators_not_spaced() -> None:
    """The trap: a spaced encoding hashes to a wrong-but-plausible hex string."""
    nonce = "cd" * 16
    spaced = hashlib.sha256(
        (json.dumps(TERMS, sort_keys=True) + "|" + nonce).encode("utf-8")).hexdigest()
    assert reference_commit(TERMS, nonce) != spaced


def test_game_id_is_lexicographic_and_symmetric() -> None:
    assert reference_game_id("uoh-sqak", "ahk-yosi") == "ahk-yosi-vs-uoh-sqak"
    assert reference_game_id("ahk-yosi", "uoh-sqak") == "ahk-yosi-vs-uoh-sqak"


def test_game_uid_is_deterministic_symmetric_and_terms_bound() -> None:
    a = reference_game_uid(TERMS, "ahk-yosi", "uoh-sqak")
    assert a == reference_game_uid(TERMS, "uoh-sqak", "ahk-yosi")  # order cannot matter
    assert uuid.UUID(a)  # a real UUID string, not a bare hex slice
    material = canonical_bytes(TERMS) + b"|ahk-yosi|uoh-sqak"
    assert a == str(uuid.UUID(bytes=sha256_raw(material)[:16]))
    assert a != reference_game_uid({**TERMS, "max_steps": 36}, "ahk-yosi", "uoh-sqak")


def test_signature_uses_default_separators() -> None:
    """Their §7 signs json.dumps DEFAULTS - the opposite of the commit encoding."""
    result = {"game_id": "a-vs-b", "aggregate": {}, "sub_games": []}
    doc = signature_document(result)
    assert mutual_signature(result) == hashlib.sha256(
        json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert spaced_bytes(doc) != canonical_bytes(doc)


def test_only_the_five_row_keys_reach_the_signature() -> None:
    """Rows may carry commits, clocks and tokens without moving the digest."""
    lean = {"game_id": "a-vs-b",
            "aggregate": {"total_score": {"a": 45}, "sub_games_won": {"a": 0},
                          "ties": 6, "winner_group": None, "series_tie": True},
            "sub_games": [{"sub_game_number": 1, "roles": {"a": "police"},
                           "result": "survival", "winner_group": "b",
                           "score": {"a": 5, "b": 10}}]}
    noisy = json.loads(json.dumps(lean))
    noisy["sub_games"][0].update(github_commit="deadbeef", tokens=812, audit="Verified OK")
    noisy["generated_at"] = "2026-08-09T12:00:00Z"
    assert mutual_signature(noisy) == mutual_signature(lean)


def _row(index: int, ending: str, winner: str, cop: int, thief: int) -> dict:
    return {"index": index, "ending": ending, "winner": winner,
            "cop_score": cop, "thief_score": thief}


def test_signed_row_follows_the_role_we_actually_played() -> None:
    """Under alternation a role-keyed score says nothing about which team scored."""
    as_cop = signed_row_fields(_row(1, "capture", "police", 20, 0),
                               my_group="ahk-yosi", their_group="uoh-sqak",
                               my_role="police")
    assert as_cop["roles"] == {"ahk-yosi": "police", "uoh-sqak": "thief"}
    assert as_cop["score"] == {"ahk-yosi": 20, "uoh-sqak": 0}
    assert as_cop["winner_group"] == "ahk-yosi"

    # Same row, same police win - but on this sub-game the police is THEM.
    as_thief = signed_row_fields(_row(2, "capture", "police", 20, 0),
                                 my_group="ahk-yosi", their_group="uoh-sqak",
                                 my_role="thief")
    assert as_thief["roles"] == {"ahk-yosi": "thief", "uoh-sqak": "police"}
    assert as_thief["score"] == {"ahk-yosi": 0, "uoh-sqak": 20}
    assert as_thief["winner_group"] == "uoh-sqak"


def test_a_sub_game_nobody_won_is_a_tie_not_a_win() -> None:
    row = signed_row_fields(_row(1, "technical_loss", "none", 0, 0),
                            my_group="a", their_group="b", my_role="police")
    assert row["winner_group"] is None
    agg = signed_aggregate([row], my_group="a", their_group="b")
    assert (agg["ties"], agg["sub_games_won"]) == (1, {"a": 0, "b": 0})


def test_aggregate_totals_and_series_tie() -> None:
    rows = [signed_row_fields(_row(1, "survival", "thief", 5, 10),
                              my_group="a", their_group="b", my_role="police"),
            signed_row_fields(_row(2, "survival", "thief", 5, 10),
                              my_group="a", their_group="b", my_role="thief")]
    agg = signed_aggregate(rows, my_group="a", their_group="b")
    assert agg["total_score"] == {"a": 15, "b": 15}      # 5 as cop + 10 as thief
    assert agg["sub_games_won"] == {"a": 1, "b": 1}
    assert agg["series_tie"] is True
    assert agg["winner_group"] is None


def test_aggregate_names_a_winner_when_totals_differ() -> None:
    rows = [signed_row_fields(_row(1, "capture", "police", 20, 0),
                              my_group="a", their_group="b", my_role="police")]
    agg = signed_aggregate(rows, my_group="a", their_group="b")
    assert (agg["winner_group"], agg["series_tie"]) == ("a", False)


def test_missing_row_key_is_explicit_null_not_absent() -> None:
    doc = signature_document({"game_id": "a-vs-b", "sub_games": [{"sub_game_number": 1}]})
    assert doc["sub_games"][0] == {"sub_game_number": 1, "roles": None, "result": None,
                                   "winner_group": None, "score": None}


def test_an_empty_agreement_reports_absence_not_disagreement() -> None:
    """Measured live: an empty agreement made all 14 terms look mismatched.

    Absence and disagreement need different remedies - one means "your peer said
    nothing", the other means "your game.json differs" - so they must not arrive
    as the same two refusal messages.
    """
    from p2p_pursuit.infra.interop_codec import handshake_from_agreement

    terms = {"board_size": 7, "max_steps": 35}
    empty = handshake_from_agreement({}, mine={"role": "police"}, terms=terms)
    assert empty["agreement_empty"] is True

    real = handshake_from_agreement(
        {"terms": terms, "nonce": "ab" * 16,
         "signature": reference_commit(terms, "ab" * 16)},
        mine={"role": "police"}, terms=terms)
    assert real["agreement_empty"] is False
    assert real["terms_match"] and real["signature_verified"]


# -- amireman: the series-consensus object (their §10-11) ---------------------
# A third digest over the same finished series, and the one whose failure mode
# is silence: a wrong encoding still produces 64 valid hex characters, so the
# only way to know ours is right is to reproduce a document they published.

APPENDIX_C_ROWS = [
    (1, "survival", "thief", "police", 10, 5, "teamA"),
    (2, "capture", "police", "thief", 20, 5, "teamA"),
    (3, "survival", "thief", "police", 10, 5, "teamA"),
    (4, "survival", "police", "thief", 5, 10, "teamB"),
    (5, "capture", "thief", "police", 5, 20, "teamB"),
    (6, "survival", "police", "thief", 5, 10, "teamB"),
]


def _our_rows() -> list[dict]:
    """Our own sub-game row shape, as `finish_sub_game` leaves it."""
    return [{"index": i, "ending": ending, "roles": {"teamA": ra, "teamB": rb},
             "score": {"teamA": sa, "teamB": sb}, "winner_group": winner}
            for i, ending, ra, rb, sa, sb, winner in APPENDIX_C_ROWS]


def test_consensus_object_reproduces_their_appendix_c() -> None:
    from p2p_pursuit.report.consensus import consensus_document

    doc = consensus_document(game_id="EXAMPLE001", game_uid="u", rows=_our_rows())
    assert list(doc) == ["game_id", "game_uid", "sub_games"]
    assert doc["sub_games"][0] == {
        "sub_game_number": 1, "result": "survival",
        "roles": {"teamA": "thief", "teamB": "police"},
        "score": {"teamA": 10, "teamB": 5}, "winner_group": "teamA"}
    from p2p_pursuit.report.consensus import ROW_KEYS

    assert all(set(row) == set(ROW_KEYS) for row in doc["sub_games"])


def test_consensus_sha_uses_compact_separators_not_the_signature_encoding() -> None:
    """The trap that makes this a separate module: the *mutual signature* over
    the same series is spaced, this one is compact. Both are 64 hex."""
    from p2p_pursuit.report.consensus import consensus_document, consensus_sha

    doc = consensus_document(game_id="EXAMPLE001", game_uid="u", rows=_our_rows())
    expected = hashlib.sha256(json.dumps(
        doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    assert consensus_sha(doc) == expected
    assert consensus_sha(doc) != hashlib.sha256(spaced_bytes(doc)).hexdigest()


def test_consensus_rows_are_sorted_by_sub_game_number() -> None:
    from p2p_pursuit.report.consensus import consensus_document

    shuffled = list(reversed(_our_rows()))
    doc = consensus_document(game_id="g", game_uid="u", rows=shuffled)
    assert [row["sub_game_number"] for row in doc["sub_games"]] == [1, 2, 3, 4, 5, 6]


def test_technical_loss_survives_verbatim_unlike_the_mutual_signature() -> None:
    """`mutual_signature` aliases it to "timeout" for a peer whose vocabulary
    lacks it; this contract lists it, so aliasing here would file the wrong
    result under a digest that still looks well-formed."""
    from p2p_pursuit.report.consensus import consensus_row

    row = {"index": 1, "ending": "technical_loss", "roles": {}, "score": {},
           "winner_group": None}
    assert consensus_row(row)["result"] == "technical_loss"
    assert signed_row_fields(
        {"index": 1, "ending": "technical_loss", "winner": "none",
         "cop_score": 0, "thief_score": 0},
        my_group="a", their_group="b", my_role="police")["result"] == "timeout"


def test_unknown_result_raises_rather_than_being_coerced() -> None:
    import pytest

    from p2p_pursuit.report.consensus import consensus_row

    with pytest.raises(ValueError, match="not one of"):
        consensus_row({"index": 1, "ending": "abandoned", "roles": {}, "score": {},
                       "winner_group": None})


def test_consensus_envelope_shape_and_gate() -> None:
    """Their §10.3 accepts a peer digest only on claim + sender role + no
    records, and §9 ignores a `consensus_sha` that is not 64 lowercase hex."""
    from p2p_pursuit.report.consensus import consensus_envelope, peer_consensus_sha

    sha = "a" * 64
    env = consensus_envelope(sender="thief", sha=sha)
    assert env == {"sender": "thief", "records": [],
                   "result_claim": "series_consensus", "consensus_sha": sha}
    assert peer_consensus_sha(env, peer_role="thief") == sha

    assert peer_consensus_sha(env, peer_role="police") is None
    assert peer_consensus_sha({**env, "records": [{"a": 1}]}, peer_role="thief") is None
    assert peer_consensus_sha({**env, "result_claim": "capture"}, peer_role="thief") is None
    assert peer_consensus_sha({**env, "consensus_sha": "A" * 64}, peer_role="thief") is None
    assert peer_consensus_sha({**env, "consensus_sha": "abc"}, peer_role="thief") is None


def test_absent_digest_is_omitted_not_null() -> None:
    from p2p_pursuit.report.consensus import consensus_envelope

    assert "consensus_sha" not in consensus_envelope(sender="police", sha=None)
