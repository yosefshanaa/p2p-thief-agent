"""Mutual post-game audit: every sealed record is re-verified (book ch. 5.4).

A single mismatch - hash, trajectory, physics, scent honesty or a capture
lie - yields TAMPERED and a technical forfeit. Cryptography, not judgement.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from .board import MOVES, Board, Cell
from .crypto import digest, verify
from .protocol import KIND_CAPTURE_ANSWER, KIND_CAPTURED_EVENT, KIND_STEP
from .rules import Decision, validate
from .scent import ScentField

VERIFIED_OK = "Verified OK"
TAMPERED = "TAMPERED"


def verify_entry(entry: dict[str, Any], commit_hash: str) -> bool:
    """One replay-viewer step: does the revealed record still match its commitment?"""
    return verify(entry, commit_hash)


def audit_opponent(
    *,
    entries: list[dict[str, Any]],
    live_hashes: list[str],
    live_public: list[dict[str, Any] | None],
    role: str,
    start_pos: Cell,
    grid_size: int,
    quota: int,
    barriers_before_step: Callable[[int], set[Cell]],
) -> tuple[str, list[str]]:
    """Re-verify the opponent's full revealed log against what we saw live.

    ``barriers_before_step(k)`` returns every barrier (both sides) already
    declared before the opponent's step ``k`` - physics at the right moment.
    """
    v: list[str] = []
    if len(entries) != len(live_hashes):
        return TAMPERED, [f"record count {len(entries)} != received hashes {len(live_hashes)}"]

    steps = [e for e in entries if e.get("kind") == KIND_STEP]
    field = ScentField(grid_size)
    expected_pos = list(start_pos)
    barriers_placed = 0

    # Content-addressed pairing: record order may legally differ from arrival
    # order across concurrent peers, so match each sealed record to the live
    # commitment multiset by its digest instead of by position.
    available = Counter(live_hashes)
    pub_by_hash: dict[str, dict[str, Any]] = {}
    for h, pub in zip(live_hashes, live_public, strict=False):
        if pub is not None and h not in pub_by_hash:
            pub_by_hash[h] = pub
    for i, entry in enumerate(entries):
        d = digest(entry)
        if available.get(d, 0) > 0:
            available[d] -= 1
        else:
            v.append(f"record {i}: hash mismatch (tampering)")
            continue
        pub = pub_by_hash.get(d)
        if pub is not None:
            for key in ("hint", "scent", "barrier", "kind", "step", "at_step"):
                if key in pub and key in entry and pub[key] != entry[key]:
                    v.append(f"record {i}: revealed {key} differs from sealed {key}")

    for k, entry in enumerate(steps, start=1):
        if entry["step"] != k:
            v.append(f"step {k}: numbered {entry['step']}")
        if list(entry["pos_before"]) != expected_pos:
            v.append(f"step {k}: trajectory break {entry['pos_before']} != {expected_pos}")
        board = Board(grid_size, set(barriers_before_step(k)))
        barrier = tuple(entry["barrier"]) if entry["barrier"] else None
        decision = Decision(move=entry["move"], barrier=barrier)
        pos_before = tuple(entry["pos_before"])
        reason = validate(board, role, pos_before, decision, barriers_placed, quota)
        if reason:
            v.append(f"step {k}: illegal - {reason}")
        if barrier:
            barriers_placed += 1
            expected_after = list(entry["pos_before"])
        else:
            dr, dc = MOVES.get(entry["move"], (0, 0))
            expected_after = [pos_before[0] + dr, pos_before[1] + dc]
        if list(entry["pos_after"]) != expected_after:
            v.append(f"step {k}: pos_after {entry['pos_after']} inconsistent with move")
        if entry["scent"] != field.snapshot():
            v.append(f"step {k}: served scent field does not match recomputation")
        field.emit(tuple(entry["pos_after"]))
        field.decay()
        expected_pos = list(entry["pos_after"])

    pos_after_step = {e["step"]: tuple(e["pos_after"]) for e in steps}
    for entry in entries:
        if entry.get("kind") == KIND_CAPTURE_ANSWER:
            true_pos = pos_after_step.get(entry["at_step"], tuple(start_pos))
            truthful = list(true_pos) == list(entry["claim_cell"])
            if bool(entry["answer"]) != truthful:
                v.append(f"capture answer at step {entry['at_step']}: dishonest (rule #21)")
        if entry.get("kind") == KIND_CAPTURED_EVENT and entry["cause"] == "barrier":
            true_pos = pos_after_step.get(entry["at_step"], tuple(start_pos))
            if tuple(true_pos) not in barriers_before_step(entry["at_step"] + 1):
                v.append(f"captured_event at step {entry['at_step']}: cell was not barred")

    return (VERIFIED_OK, []) if not v else (TAMPERED, v)
