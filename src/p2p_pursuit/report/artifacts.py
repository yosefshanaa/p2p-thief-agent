"""Writers for the four standardized JSON artifacts (book Appendix F #3).

declaration_<game_id>.json | config_<game_id>_gNN.json |
log_<game_id>_gNN.json     | result_<game_id>.json
All share the game_uid so files from different games can never mix.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain.game_ids import config_name, declaration_name, result_name


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_declaration(out_dir: Path, game_id: str, declaration: dict[str, Any]) -> Path:
    return _write(out_dir / declaration_name(game_id), declaration)


def write_config_copy(out_dir: Path, game_id: str, sub_game: int,
                      shared_raw: dict[str, Any], game_uid: str) -> Path:
    payload = {"game_uid": game_uid, "game_id": game_id, "sub_game": sub_game,
               "config": shared_raw}
    return _write(out_dir / config_name(game_id, sub_game), payload)


def write_result(out_dir: Path, game_id: str, result: dict[str, Any]) -> Path:
    return _write(out_dir / result_name(game_id), result)
