"""Artifact writing for the in-process sim series.

The sim produces the same four artifacts a networked match does; keeping that
assembly here leaves `cli` the thin argument-parsing shell the guidelines ask
for (ch. 4: no business logic above the SDK).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..peer import log_manager
from ..shared import sysinfo
from . import artifacts, results


def sub_game_writer(*, out: Path, game_uid: str, game_id: str, shared: Any,
                    rows: list[dict[str, Any]], log_fn: Any) -> Any:
    """Build the per-sub-game callback the local series runner invokes."""

    def per_sub_game(police: Any, thief: Any, outcome: Any) -> None:
        audit = {"mine_of_them": outcome.audit_of_thief,
                 "theirs_of_us": outcome.audit_of_police}
        log = log_manager.build_log(police, thief.my_records, game_uid=game_uid,
                                    game_id=game_id, audit=audit)
        log_manager.write_log(log, out)
        artifacts.write_config_copy(out, game_id, outcome.index, shared.raw, game_uid)
        rows.append(results.sub_game_row(
            index=outcome.index, ending=outcome.ending, winner=outcome.winner,
            cause=outcome.cause, police_score=outcome.police_score,
            thief_score=outcome.thief_score, moves_played=outcome.thief_steps,
            github_commit=sysinfo.git_commit(),
            audit_verdict=outcome.audit_of_thief["verdict"],
            opponent_audit=outcome.audit_of_police["verdict"]))
        log_fn(f"[sim] g{outcome.index}: {outcome.ending} winner={outcome.winner} "
               f"({outcome.cause})")

    return per_sub_game
