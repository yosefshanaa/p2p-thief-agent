"""Commit-reveal primitives: canonical serialization, sealing, verification.

Single entry point for every hashed payload in the system (PLAN ADR-5):
commits, config locks, scent-model locks and step-0 declarations all pass
through :func:`canonical_bytes` so both peers hash byte-identical input.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

NONCE_HEX_BYTES = 16

#: Our digest: the nonce lives inside the record, and the whole thing is hashed.
NATIVE = "native"
#: The reference implementation's digest: ``sha256(canonical(payload)|nonce)``,
#: nonce outside the JSON. Selectable per match so an unmodified reference peer
#: can audit our log on its own terms (RUNBOOK 3b); it changes only how the
#: commitment is *composed*, never what is committed to or how binding it is.
REFERENCE = "reference"


def canonical_bytes(obj: Any) -> bytes:
    """Serialize ``obj`` as canonical JSON: sorted keys, fixed separators, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(obj: Any) -> str:
    """SHA-256 hex digest of the canonical form of ``obj``."""
    return sha256_hex(canonical_bytes(obj))


def new_nonce() -> str:
    """Fresh cryptographic nonce (defeats dictionary attacks over the small move space)."""
    return secrets.token_hex(NONCE_HEX_BYTES)


def reference_commit(payload: dict[str, Any], nonce: str) -> str:
    """The reference implementation's commitment over a nonce-free payload."""
    return sha256_hex(canonical_bytes(payload) + b"|" + nonce.encode("utf-8"))


def verify_reference_record(record: dict[str, Any]) -> bool:
    """Verify one record in their ``{payload, nonce, commit}`` reveal envelope."""
    try:
        return secrets.compare_digest(
            reference_commit(record["payload"], record["nonce"]), record["commit"])
    except (KeyError, TypeError, AttributeError):
        return False


def commit_digest(sealed_record: dict[str, Any], dialect: str = NATIVE) -> str:
    """Commitment for one sealed record under the agreed digest dialect."""
    if dialect == REFERENCE:
        payload = {k: v for k, v in sealed_record.items() if k != "nonce"}
        return reference_commit(payload, sealed_record["nonce"])
    return digest(sealed_record)


def seal(record: dict[str, Any], dialect: str = NATIVE) -> tuple[dict[str, Any], str]:
    """Attach a fresh nonce to ``record`` and return (sealed_record, commit_hash).

    The returned record includes the nonce and must stay private until the
    audit; only the hash travels at commit time.
    """
    sealed = dict(record)
    sealed["nonce"] = new_nonce()
    return sealed, commit_digest(sealed, dialect)


def verify(sealed_record: dict[str, Any], commit_hash: str,
           dialect: str = NATIVE) -> bool:
    """Recompute the hash of a revealed record and compare (timing-safe)."""
    return secrets.compare_digest(commit_digest(sealed_record, dialect), commit_hash)
