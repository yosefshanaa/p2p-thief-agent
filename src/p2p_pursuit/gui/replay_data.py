"""Replay logic (pure): timeline reconstruction + per-record hash verification.

The viewer's worth is not the drawing but the live re-verification: every
record is re-hashed against the commitment received during play; one
mismatch flips the whole match to TAMPERED (book ch. 7.4, rule #20).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..domain.audit import TAMPERED, VERIFIED_OK
from ..domain.crypto import NATIVE, REFERENCE, commit_digest, verify_reference_record
from ..domain.protocol import KIND_STEP


def load_log(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_side(records: list[dict], hashes: list[str],
                dialect: str = NATIVE) -> list[bool]:
    """Content-addressed: each record must match one live-received commitment."""
    available = Counter(hashes)
    marks = []
    for record in records:
        d = commit_digest(record, dialect)
        ok = available.get(d, 0) > 0
        if ok:
            available[d] -= 1
        marks.append(ok)
    return marks


def opponent_display(log: dict[str, Any],
                     marks: list[bool]) -> tuple[list[dict[str, Any]], list[bool]]:
    """The opponent's records and their verification marks, in our display shape.

    An interop opponent reveals ``{payload, nonce, commit}`` envelopes holding
    their own field names; unwrapping them here is what keeps both sides of the
    match visible in the replay rather than only ours. Marks are filtered
    alongside the records so the two never drift apart.
    """
    if log.get("commit_dialect", NATIVE) != REFERENCE:
        return log["opponent_records"], marks
    other = "thief" if log.get("perspective") == "police" else "police"
    out, kept = [], []
    for record, ok in zip(log["opponent_records"], marks, strict=False):
        payload = record.get("payload", {})
        if "position" not in payload:
            continue  # their step-0 system_spec record has no move to draw
        out.append({"kind": KIND_STEP, "role": other, "step": payload.get("step", 0),
                    "pos_after": list(payload["position"]), "barrier": None,
                    "hint": payload.get("hint", ""),
                    "intent": payload.get("intent", "")})
        kept.append(ok)
    return out, kept


def _verify_reference_side(records: list[dict], hashes: list[str]) -> tuple[list[bool], bool]:
    """Their envelope: each record binds to its own commit, and every commitment
    we witnessed live must be among those revealed - their own audit checks only
    the first half, so a withheld step would otherwise pass unnoticed."""
    marks = [verify_reference_record(record) for record in records]
    revealed = {record.get("commit") for record in records}
    return marks, all(h in revealed for h in hashes)


def verdict_of(log: dict[str, Any]) -> tuple[str, list[bool], list[bool]]:
    # Logs written before interop mode existed carry no marker and are native.
    dialect = log.get("commit_dialect", NATIVE)
    mine = verify_side(log["my_records"], log["my_hashes"], dialect)
    if dialect == REFERENCE:
        theirs, complete = _verify_reference_side(
            log["opponent_records"], log["opponent_hashes"])
    else:
        theirs = verify_side(log["opponent_records"], log["opponent_hashes"], dialect)
        complete = len(log["opponent_records"]) == len(log["opponent_hashes"])
    ok = all(mine) and all(theirs) and complete
    return (VERIFIED_OK if ok else TAMPERED), mine, theirs


def timeline(log: dict[str, Any]) -> list[dict[str, Any]]:
    """Merged, ordered step list for display: thief step k before police step k."""
    _, mine_ok, theirs_ok = verdict_of(log)
    opp_records, opp_ok = opponent_display(log, theirs_ok)
    items = []
    for records, marks, owner in ((log["my_records"], mine_ok, "mine"),
                                  (opp_records, opp_ok, "opponent")):
        for record, ok in zip(records, marks, strict=False):
            if record.get("kind") != KIND_STEP:
                continue
            items.append({
                "role": record["role"], "step": record["step"],
                "pos_after": tuple(record["pos_after"]),
                "barrier": tuple(record["barrier"]) if record.get("barrier") else None,
                "hint": record.get("hint", ""), "intent": record.get("intent", ""),
                "verified": ok, "owner": owner,
            })
    order = {"thief": 0, "police": 1}
    items.sort(key=lambda it: (it["step"], order.get(it["role"], 2)))
    return items


def frames(log: dict[str, Any]) -> list[dict[str, Any]]:
    """Cumulative board frames: positions + barriers after each timeline item."""
    positions: dict[str, tuple[int, int]] = {}
    barriers: set[tuple[int, int]] = set()
    out = []
    for item in timeline(log):
        positions[item["role"]] = item["pos_after"]
        if item["barrier"]:
            barriers.add(item["barrier"])
        out.append({**item, "positions": dict(positions), "barriers": set(barriers)})
    return out
