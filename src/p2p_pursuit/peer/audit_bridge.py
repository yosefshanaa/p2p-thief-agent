"""Bridges a TurnEngine to the domain audit: packaging and timeline reconstruction."""

from __future__ import annotations

from typing import Any

from ..domain.audit import audit_opponent
from ..domain.board import Cell
from ..domain.rules import POLICE
from .turn_engine import TurnEngine


def audit_package(engine: TurnEngine) -> dict[str, Any]:
    """Everything the opponent needs to audit us: the full sealed log, nonces included."""
    return {
        "kind": "audit_package",
        "role": engine.role,
        "sub_game": engine.sub_game,
        "records": engine.my_records,
    }


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
        live_hashes=engine.opp_hashes,
        live_public=engine.opp_public,
        role=engine.other,
        start_pos=opp_start,
        grid_size=engine.shared.grid_size,
        quota=engine.shared.max_barriers,
        barriers_before_step=_barriers_before_step(engine),
        dialect=engine.commit_dialect,
        scent_model=engine.own_field.model,
    )
