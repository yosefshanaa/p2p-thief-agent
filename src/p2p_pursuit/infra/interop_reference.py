"""Sealing and auditing in the reference dialect.

Split out of :mod:`.interop_codec` (§3.2 - split, never compress). One concern:
their commit formula and the audit built on it. Theirs hashes
``canonical(payload)|nonce``; ours puts the nonce inside the record, so neither
side can verify the other until one adopts the other's digest - which is what
this module is for.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..domain.crypto import reference_commit, verify_reference_record
from .interop_grid import grid_to_scent, scent_to_grid

log = logging.getLogger(__name__)


# The formula itself lives in domain.crypto, which owns every digest in the
# system; these helpers wrap it in the record envelope their audit expects.
def reference_records(sealed_records: list[dict[str, Any]],
                      live_hashes: list[str] | None = None) -> list[dict[str, Any]]:
    """Our sealed records -> their ``{payload, nonce, commit}`` audit format.

    Only the envelope changes: the payload is our record, so what we committed
    to is exactly what we played.

    ``commit`` is the commitment **we actually sent live**, not one re-derived
    here. Re-deriving is what makes a broken reveal look healthy: every record
    still verifies against its own recomputed hash, so the package passes any
    self-check, while binding to nothing the opponent holds. Recomputation is
    still done - as a comparison, so a divergence is a loud mismatch at the
    moment of sending instead of a silent 0-of-N in their audit.
    """
    hashes = list(live_hashes or [])
    out = []
    for index, sealed in enumerate(sealed_records):
        payload = {k: v for k, v in sealed.items() if k != "nonce"}
        derived = reference_commit(payload, sealed["nonce"])
        live = hashes[index] if index < len(hashes) else None
        if live is not None and live != derived:
            log.error("record %d: the sealed payload no longer hashes to the "
                      "commitment we sent (%s != %s) - revealing the live one",
                      index, derived[:16], live[:16])
        out.append({"payload": payload, "nonce": sealed["nonce"],
                    "commit": live or derived})
    return out


def reference_verify(record: dict[str, Any]) -> bool:
    """Re-hash one revealed ``{payload, nonce, commit}`` record on their terms."""
    return verify_reference_record(record)


def reference_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a whole reference-format log; mirrors their ``audit_records`` report."""
    failed = [record["payload"].get("step", -1)
              for record in records if not reference_verify(record)]
    return {"passed": not failed, "verified_steps": len(records) - len(failed),
            "failed_steps": failed}


# -- our commit + reveal -> their TurnMessage --------------------------------
def to_turn_message(reveal: dict[str, Any], *, commit_hash: str | None = None,
                    claim_response: dict | None = None,
                    win_claim: dict | None = None,
                    timestamp: str | None = None) -> dict[str, Any]:
    """Fold one of our steps into the single message their peer expects.

    ``claim_response`` and ``win_claim`` are what we owe them from *their*
    previous message; their protocol carries both as plain fields on the next
    turn, so neither is bound by their commit (see the interop notes).
    """
    claim = reveal.get("claim")
    return {
        "step": reveal["step"],
        "sender": reveal["role"],
        "hint": reveal.get("hint", ""),
        "smell_grid": scent_to_grid(reveal.get("scent") or []),
        "commit": commit_hash or reveal.get("hash", ""),
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "barrier_placed": list(reveal["barrier"]) if reveal.get("barrier") else None,
        "capture_claim": list(claim["cell"]) if claim else None,
        "claim_response": claim_response,
        "win_claim": win_claim,
    }


# -- their TurnMessage -> our commit + reveal --------------------------------
def from_turn_message(message: dict[str, Any], *, sub_game: int,
                      grid_size: int) -> dict[str, Any]:
    """Split their turn into the two messages our engine handlers consume.

    Returns ``{commit, reveal, claim_response, win_claim}``; the last two are
    side channels the engine has no inbound handler for, so the bridge applies
    them itself.
    """
    sender, step = message["sender"], message["step"]
    commit_hash = message.get("commit", "")
    reveal: dict[str, Any] = {
        "kind": "step", "role": sender, "sub_game": sub_game, "step": step,
        "barrier": list(message["barrier_placed"]) if message.get("barrier_placed") else None,
        "hint": message.get("hint", ""),
        "scent": grid_to_scent(message.get("smell_grid") or {}, grid_size),
        "hash": commit_hash,
        # Their clock, stamped by them on the turn itself. Outside their commit
        # and therefore untrusted as evidence - but it is the only timing in the
        # match sourced from the other side, so it is kept and filed as theirs
        # rather than discarded.
        "timestamp": message.get("timestamp"),
    }
    if message.get("capture_claim"):
        reveal["claim"] = {"cell": list(message["capture_claim"]), "at_step": step}
    return {
        "commit": {"kind": "commit", "role": sender, "sub_game": sub_game,
                   "step": step, "hash": commit_hash},
        "reveal": reveal,
        "claim_response": message.get("claim_response"),
        "win_claim": message.get("win_claim"),
    }
