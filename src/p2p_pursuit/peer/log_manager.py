"""Sub-game log artifact: the sealed step-by-step record the replay viewer verifies.

Written after the mutual audit, when nonces are legitimately revealed; the
file carries both sides' records plus the live-received hashes so every
entry can be re-verified independently (book ch. 7).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain.game_ids import log_name
from ..shared.version import CODE_VERSION
from .turn_engine import TurnEngine


def build_log(engine: TurnEngine, opponent_records: list[dict[str, Any]],
              *, game_uid: str, game_id: str,
              audit: dict[str, Any]) -> dict[str, Any]:
    end = engine.end
    return {
        "report_type": "sub_game_log",
        "game_uid": game_uid,
        "game_id": game_id,
        "sub_game": engine.sub_game,
        "perspective": engine.role,
        "code_version": CODE_VERSION,
        "config_sha256": engine.shared.sha256,
        "my_records": engine.my_records,
        "my_hashes": engine.my_hashes,
        "opponent_records": opponent_records,
        "opponent_hashes": engine.opp_hashes,
        "result": None if end is None else
        {"ending": end.ending, "winner": end.winner, "cause": end.cause,
         "my_steps": engine.my_steps, "opp_steps": engine.opp_steps},
        "audit": audit,
        "tokens_used": engine.tokens_used,
    }


def write_log(log: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / log_name(log["game_id"], log["sub_game"])
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
