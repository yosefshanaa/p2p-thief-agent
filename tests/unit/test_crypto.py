"""Crypto primitives: canonical stability, seal/verify, tamper sensitivity."""

from p2p_pursuit.domain.crypto import canonical_bytes, digest, new_nonce, seal, verify


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
