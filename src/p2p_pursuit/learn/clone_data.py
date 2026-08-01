"""Turn a played match into a labelled dataset of the opponent's decisions.

After the audit exchange both sides hold the other's sealed records, and a step
record carries the position and the move. So a finished match is not just a
result - it is a few hundred rows of *this team chose this move from this
state*, which is the one thing a simulator built out of our own brains cannot
invent.

Two dialects appear here: our native record, and the reference envelope
``{payload, nonce, commit}`` whose payload names the move ``MOVE:S``. Both are
read, because a league mixes them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.board import MOVES, Cell
from ..domain.rules import POLICE, THIEF

BARRIERS_IN_STATE = re.compile(r"barriers=(\[.*?\])\s*(?:;|$)")


@dataclass(frozen=True)
class Sample:
    """One observed decision, in the terms a brain would have seen it."""

    role: str
    pos: Cell            # where they stood when they decided
    pursuer: Cell        # where we stood at that moment (their actual threat)
    barriers: tuple[Cell, ...]
    move: str
    prev_move: str | None
    size: int


def _move_of(raw: Any) -> str | None:
    text = str(raw or "").upper().removeprefix("MOVE:").strip()
    return text if text in MOVES else None


def _barriers_of(payload: dict) -> list[Cell]:
    if isinstance(payload.get("barriers"), list):
        return [tuple(c) for c in payload["barriers"]]
    found = BARRIERS_IN_STATE.search(str(payload.get("state", "")))
    if not found:
        return []
    try:
        return [tuple(c) for c in json.loads(found.group(1))]
    except (ValueError, TypeError):
        return []


def _steps(records: list[dict]) -> list[dict]:
    """Normalise either dialect to {step, pos, move, barrier, barriers}."""
    out = []
    for record in records:
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
        move = _move_of(payload.get("move"))
        position = payload.get("pos_after") or payload.get("position")
        if move is None or not isinstance(position, list) or len(position) != 2:
            continue
        out.append({"step": int(payload.get("step", len(out) + 1)),
                    "pos": tuple(position), "move": move,
                    "barrier": payload.get("barrier"),
                    "barriers": _barriers_of(payload)})
    return sorted(out, key=lambda s: s["step"])


def samples_from_log(log: dict, size: int = 7) -> list[Sample]:
    """Every opponent decision in one sealed sub-game log."""
    mine, theirs = _steps(log.get("my_records", [])), _steps(log.get("opponent_records", []))
    if not theirs:
        return []
    my_role = log.get("perspective") or (log.get("my_records") or [{}])[0].get("role") or POLICE
    their_role = THIEF if my_role == POLICE else POLICE
    walls: set[Cell] = set()
    samples, prev_move, prev_pos = [], None, None
    for record in theirs:
        walls.update(record["barriers"])
        walls.update(tuple(s["barrier"]) for s in mine
                     if s["step"] < record["step"] and s["barrier"])
        # Their decision was taken from where the previous record left them,
        # against wherever we stood at the end of our previous turn.
        pursuer = next((s["pos"] for s in reversed(mine) if s["step"] < record["step"]), None)
        if prev_pos is not None and pursuer is not None:
            samples.append(Sample(role=their_role, pos=prev_pos, pursuer=pursuer,
                                  barriers=tuple(sorted(walls)), move=record["move"],
                                  prev_move=prev_move, size=size))
        prev_move, prev_pos = record["move"], record["pos"]
    return samples


def samples_from_match(directory: Path, size: int = 7) -> list[Sample]:
    """Every opponent decision across a match directory of sealed logs."""
    out: list[Sample] = []
    for path in sorted(directory.rglob("log_*.json")):
        out.extend(samples_from_log(json.loads(path.read_text(encoding="utf-8")), size))
    return out
