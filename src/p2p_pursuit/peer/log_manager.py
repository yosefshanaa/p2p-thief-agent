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
              audit: dict[str, Any],
              package: dict[str, Any] | None = None) -> dict[str, Any]:
    """The sealed artifact for one sub-game.

    ``package`` is the frozen reveal that was actually sent for this sub-game.
    Preferred over the live engine because the log is written *after* the audit
    exchange, by which point the opponent's first turn of the next sub-game can
    already have reset the engine - and a log whose records are not the ones we
    revealed is not evidence of anything.
    """
    end = engine.end
    frozen = package or engine.audit_snapshot()
    n = frozen.get("sub_game", engine.sub_game)
    return {
        "report_type": "sub_game_log",
        "game_uid": game_uid,
        "game_id": game_id,
        "sub_game": n,
        "perspective": frozen.get("role", engine.role),
        "code_version": CODE_VERSION,
        "config_sha256": engine.shared.sha256,
        "commit_dialect": engine.commit_dialect,
        # This sub-game's own clock. `started_at`/`ended_at` are ours, taken when
        # the sub-game opened and when it ended; `opponent_turn_timestamps` are
        # theirs, stamped on each turn message, kept unmodified and named as
        # theirs because they ride outside their commitment.
        "started_at": frozen.get("started_at"),
        "ended_at": frozen.get("ended_at"),
        "opponent_turn_timestamps": frozen.get(
            "opp_turn_times", engine.opp_turn_times),
        "my_records": frozen.get("records", engine.my_records),
        "my_hashes": frozen.get("hashes", engine.my_hashes),
        "opponent_records": opponent_records,
        "opponent_hashes": engine.opponent_hashes_for(n),
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
