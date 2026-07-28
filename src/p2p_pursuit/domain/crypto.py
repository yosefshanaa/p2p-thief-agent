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


def seal(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Attach a fresh nonce to ``record`` and return (sealed_record, commit_hash).

    The returned record includes the nonce and must stay private until the
    audit; only the hash travels at commit time.
    """
    sealed = dict(record)
    sealed["nonce"] = new_nonce()
    return sealed, digest(sealed)


def verify(sealed_record: dict[str, Any], commit_hash: str) -> bool:
    """Recompute the hash of a revealed record and compare (timing-safe)."""
    return secrets.compare_digest(digest(sealed_record), commit_hash)
