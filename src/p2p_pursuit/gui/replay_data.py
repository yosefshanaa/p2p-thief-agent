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
from ..domain.crypto import digest
from ..domain.protocol import KIND_STEP


def load_log(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_side(records: list[dict], hashes: list[str]) -> list[bool]:
    """Content-addressed: each record must match one live-received commitment."""
    available = Counter(hashes)
    marks = []
    for record in records:
        d = digest(record)
        ok = available.get(d, 0) > 0
        if ok:
            available[d] -= 1
        marks.append(ok)
    return marks


def verdict_of(log: dict[str, Any]) -> tuple[str, list[bool], list[bool]]:
    mine = verify_side(log["my_records"], log["my_hashes"])
    theirs = verify_side(log["opponent_records"], log["opponent_hashes"])
    ok = all(mine) and all(theirs) and len(log["opponent_records"]) == len(
        log["opponent_hashes"])
    return (VERIFIED_OK if ok else TAMPERED), mine, theirs


def timeline(log: dict[str, Any]) -> list[dict[str, Any]]:
    """Merged, ordered step list for display: thief step k before police step k."""
    _, mine_ok, theirs_ok = verdict_of(log)
    items = []
    for records, marks, owner in ((log["my_records"], mine_ok, "mine"),
                                  (log["opponent_records"], theirs_ok, "opponent")):
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
