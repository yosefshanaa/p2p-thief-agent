"""Auditing a reference-derived opponent's revealed log.

Their own audit (`audit_records`) re-verifies hash binding and nothing else,
and their record shape is not ours, so `domain.audit.audit_opponent` cannot
read it. This is the cross-dialect verdict we can honestly reach:

1. every revealed record still binds to its own commitment;
2. every commitment we witnessed live is actually revealed - their audit has
   no such check, so a peer could otherwise withhold an inconvenient step;
3. their trajectory is physically continuous on the agreed board.

What it does NOT re-derive is scent honesty and barrier quota from their
record shape. A counted match wanting the full physics audit of ch. 5.4 must
be played in one dialect on both sides - see RUNBOOK 3b.
"""

from __future__ import annotations

from typing import Any

from ..domain.audit import TAMPERED, VERIFIED_OK
from .interop_codec import reference_verify


def _positions(records: list[dict[str, Any]]) -> list[tuple[int, list[int]]]:
    """(step, position) for every record that declares one, in step order."""
    found = [(record["payload"].get("step", -1), list(record["payload"]["position"]))
             for record in records if "position" in record.get("payload", {})]
    return sorted(found)


def audit_reference_log(records: list[dict[str, Any]], live_hashes: list[str], *,
                        grid_size: int) -> tuple[str, list[str]]:
    """Verify a reference-format log against the commitments we saw during play."""
    violations: list[str] = []

    for index, record in enumerate(records):
        if not {"payload", "nonce", "commit"} <= set(record):
            violations.append(f"record {index}: not a sealed {{payload, nonce, commit}}")
        elif not reference_verify(record):
            violations.append(f"record {index}: hash mismatch (tampering)")

    revealed = {record.get("commit") for record in records}
    for commit in live_hashes:
        if commit not in revealed:
            violations.append(f"commitment {commit[:16]}... was sent but never revealed")

    previous: list[int] | None = None
    for step, position in _positions(records):
        if not all(0 <= axis < grid_size for axis in position):
            violations.append(f"step {step}: position {position} is off the board")
        elif previous is not None:
            distance = abs(position[0] - previous[0]) + abs(position[1] - previous[1])
            if distance > 1:
                violations.append(
                    f"step {step}: jumped {previous} -> {position} in one move")
        previous = position

    return (VERIFIED_OK, []) if not violations else (TAMPERED, violations)
