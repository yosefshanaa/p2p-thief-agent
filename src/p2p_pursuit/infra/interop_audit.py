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
from ..domain.crypto import NATIVE
from ..domain.protocol import record_sub_game
from .interop_codec import reference_commit, reference_verify


def verify_outgoing_reveal(records: list[dict[str, Any]], live_hashes: list[str], *,
                           sub_game: int, role: str) -> list[str]:
    """Audit our OWN reveal the way the opponent will, before it is sent.

    This is the check amireman asked us to run locally, in their words: for
    every commitment we put on the wire during a sub-game there must be a
    revealed record whose `sha256(canonical(payload) + "|" + nonce)` reproduces
    it exactly - the same (payload, nonce) pair, not an equivalent one - and
    nothing from any other sub-game may be in the package.

    Returns the violations; empty means the package binds.
    """
    violations: list[str] = []
    by_commit: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not {"payload", "nonce", "commit"} <= set(record):
            violations.append(f"record {index}: not a sealed {{payload, nonce, commit}}")
            continue
        derived = reference_commit(record["payload"], record["nonce"])
        if derived != record["commit"]:
            violations.append(
                f"record {index}: revealed (payload, nonce) hashes to {derived[:16]}…, "
                f"not to its own commitment {str(record['commit'])[:16]}…")
        theirs = record_sub_game(record)
        if theirs is not None and theirs != sub_game:
            violations.append(
                f"record {index}: belongs to sub-game {theirs}, not {sub_game}")
        payload_role = record["payload"].get("role")
        if payload_role is not None and payload_role != role:
            violations.append(
                f"record {index}: role {payload_role!r}, but we played {role!r} "
                f"in sub-game {sub_game}")
        by_commit.setdefault(record["commit"], record)

    for commit in live_hashes:
        if commit not in by_commit:
            violations.append(
                f"commitment {commit[:16]}… was sent in play and is not revealed")
    return violations


def audit_sealed_log(log: dict[str, Any]) -> dict[str, Any]:
    """Re-run both binding checks over one sealed sub-game log, offline.

    The artifact carries what each side committed to live (`my_hashes`,
    `opponent_hashes`) next to what each side revealed, so the whole claim is
    re-checkable from the file alone, months later, by either team:

    * **ours** - every commitment we sent reproduces from the (payload, nonce)
      we revealed, under the dialect the match was played in;
    * **theirs** - every commitment they sent appears in the log they revealed;
    * **both** - no record belongs to another sub-game.
    """
    from ..domain.crypto import commit_digest

    n = log.get("sub_game")
    role = log.get("perspective")
    dialect = log.get("commit_dialect", NATIVE)
    mine: list[str] = []
    records, hashes = log.get("my_records", []), log.get("my_hashes", [])
    if len(records) != len(hashes):
        mine.append(f"{len(records)} sealed records against {len(hashes)} sent commitments")
    for index, (record, commit) in enumerate(zip(records, hashes, strict=False)):
        if commit_digest(record, dialect) != commit:
            mine.append(f"record {index}: does not reproduce the commitment we sent")
        belongs = record_sub_game(record)
        if belongs is not None and belongs != n:
            mine.append(f"record {index}: belongs to sub-game {belongs}, not {n}")
        if record.get("role") not in (None, role):
            mine.append(f"record {index}: role {record.get('role')!r}, we played {role!r}")

    theirs: list[str] = []
    revealed = {record.get("commit") for record in log.get("opponent_records", [])
                if isinstance(record, dict)}
    for commit in log.get("opponent_hashes", []):
        if log.get("opponent_records") and commit not in revealed:
            theirs.append(f"commitment {commit[:16]}… was sent in play and is not revealed")

    return {
        "sub_game": n, "role": role, "dialect": dialect,
        "records": len(records), "commitments_sent": len(hashes),
        "mine_binds": not mine, "mine_violations": mine,
        "theirs_binds": not theirs, "theirs_violations": theirs,
        "their_reveal_received": bool(log.get("opponent_records")),
    }


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
