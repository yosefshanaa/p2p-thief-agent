"""Crypto primitives: canonical stability, seal/verify, tamper sensitivity."""

import hashlib

from p2p_pursuit.domain.crypto import (
    NATIVE,
    REFERENCE,
    canonical_bytes,
    commit_digest,
    digest,
    new_nonce,
    seal,
    verify,
)


def test_canonical_is_key_order_independent():
    assert canonical_bytes({"b": 1, "a": [1, 2]}) == canonical_bytes({"a": [1, 2], "b": 1})


def test_canonical_fixed_separators_and_unicode():
    assert canonical_bytes({"a": 1, "b": "x"}) == b'{"a":1,"b":"x"}'
    assert "רמז".encode() in canonical_bytes({"hint": "רמז"})  # not ascii-escaped


def test_seal_verify_roundtrip():
    sealed, h = seal({"move": "N", "step": 1})
    assert "nonce" in sealed and len(h) == 64
    assert verify(sealed, h)


def test_nonces_unique_and_long():
    nonces = {new_nonce() for _ in range(200)}
    assert len(nonces) == 200
    assert all(len(n) == 32 for n in nonces)


def test_any_field_tamper_breaks_verification():
    sealed, h = seal({"move": "N", "step": 1, "intent": "truth", "hint": "x"})
    for key, bad in [("move", "S"), ("step", 2), ("intent", "lie"),
                     ("hint", "y"), ("nonce", "0" * 32)]:
        tampered = dict(sealed)
        tampered[key] = bad
        assert not verify(tampered, h), key


def test_digest_deterministic():
    assert digest({"x": [1, 2, 3]}) == digest({"x": [1, 2, 3]})


# -- commit dialects ---------------------------------------------------------
# Interop matches may be played under the reference implementation's digest so
# an unmodified reference peer can audit us. The native formula is what every
# artifact this project has ever written was sealed with, so it is pinned
# against an independent recomputation: changing it would silently invalidate
# every archived match log.
def test_native_commit_digest_is_unchanged_by_the_dialect_switch():
    sealed = {"move": "N", "step": 1, "nonce": "deadbeef"}
    pinned = hashlib.sha256(
        b'{"move":"N","nonce":"deadbeef","step":1}').hexdigest()
    assert digest(sealed) == pinned
    assert commit_digest(sealed) == pinned
    assert commit_digest(sealed, NATIVE) == pinned


def test_native_seal_defaults_to_the_native_dialect():
    sealed, h = seal({"move": "N", "step": 1})
    assert h == digest(sealed)


def test_reference_dialect_hashes_payload_pipe_nonce():
    """Their formula: the nonce sits OUTSIDE the canonical JSON, after a '|'."""
    sealed = {"move": "N", "step": 1, "nonce": "deadbeef"}
    payload = {"move": "N", "step": 1}
    expected = hashlib.sha256(
        canonical_bytes(payload) + b"|deadbeef").hexdigest()
    assert commit_digest(sealed, REFERENCE) == expected
    assert commit_digest(sealed, REFERENCE) != commit_digest(sealed, NATIVE)


def test_seal_and_verify_round_trip_under_the_reference_dialect():
    sealed, h = seal({"move": "E", "step": 2}, dialect=REFERENCE)
    assert verify(sealed, h, dialect=REFERENCE)
    assert not verify(sealed, h, dialect=NATIVE)


def test_reference_dialect_is_still_tamper_sensitive():
    sealed, h = seal({"move": "N", "step": 1, "hint": "x"}, dialect=REFERENCE)
    for key, bad in [("move", "S"), ("step", 2), ("hint", "y"), ("nonce", "0" * 32)]:
        tampered = dict(sealed)
        tampered[key] = bad
        assert not verify(tampered, h, dialect=REFERENCE), key
