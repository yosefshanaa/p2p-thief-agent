"""Bridges a TurnEngine to the domain audit: packaging and timeline reconstruction."""

from __future__ import annotations

from typing import Any

from ..domain.audit import audit_opponent
from ..domain.board import Cell
from ..domain.rules import POLICE
from .turn_engine import TurnEngine


def audit_package(engine: TurnEngine, sub_game: int | None = None) -> dict[str, Any]:
    """Everything the opponent needs to audit us: the sealed log, nonces included.

    Taken from the frozen ledger rather than off the running engine, and stamped
    with the sub-game it belongs to. Both matter: the engine's `my_records` is
    emptied at every boundary and refilled by the next sub-game, and a package
    that does not name its own index can only be filed by *when it arrives* -
    which is how a clean sub-game N reveal ends up audited against sub-game N+1.

    ``hashes`` are the commitments we actually put on the wire, paired with the
    records that produced them. Anything downstream reveals those bytes; it
    never re-derives a commitment at audit time.
    """
    snapshot = engine.audit_snapshot(sub_game)
    n = snapshot["sub_game"]
    records, hashes = _only_sub_game(snapshot, n)
    return {
        "kind": "audit_package",
        "role": snapshot["role"],
        "sub_game": n,
        "sub_game_number": n,
        "records": records,
        "hashes": hashes,
        # This sub-game's clock, frozen with its records. The reference bridge
        # builds its own envelope and does not forward these, so they reach the
        # log artifact without changing what goes on that dialect's wire.
        "started_at": snapshot.get("started_at"),
        "ended_at": snapshot.get("ended_at"),
        "opp_turn_times": snapshot.get("opp_turn_times", []),
    }


def _only_sub_game(snapshot: dict[str, Any], n: int) -> tuple[list[dict], list[str]]:
    """Drop anything that does not belong to sub-game ``n``, hashes in step.

    The ledger is written per sub-game, so this should never remove anything;
    it is here because "reveal only records belonging to that exact sub-game"
    is a property worth enforcing rather than assuming.
    """
    records, hashes = [], []
    for record, commit in zip(snapshot["records"], snapshot["hashes"], strict=False):
        if record.get("sub_game", n) == n:
            records.append(record)
            hashes.append(commit)
    return records, hashes


def _barriers_before_step(engine: TurnEngine) -> Any:
    """Barrier cells (both sides) declared before the *opponent's* step k."""
    history = list(engine.history)
    opponent = engine.other

    def fn(k: int) -> set[Cell]:
        cells: set[Cell] = set()
        for entry in history:
            if entry["role"] == opponent and entry["step"] >= k:
                break
            if entry["barrier"]:
                cells.add(tuple(entry["barrier"]))
        return cells

    return fn


def run_audit(engine: TurnEngine, package: dict[str, Any]) -> tuple[str, list[str]]:
    """Audit the opponent's revealed log against what we witnessed live."""
    opp_start = engine.shared.thief_start if engine.role == POLICE else engine.shared.cop_start
    return audit_opponent(
        entries=package["records"],
        live_hashes=engine.opponent_hashes_for(package.get("sub_game", engine.sub_game)),
        live_public=engine.opp_public,
        role=engine.other,
        start_pos=opp_start,
        grid_size=engine.shared.grid_size,
        quota=engine.shared.max_barriers,
        barriers_before_step=_barriers_before_step(engine),
        dialect=engine.commit_dialect,
        scent_model=engine.own_field.model,
    )
