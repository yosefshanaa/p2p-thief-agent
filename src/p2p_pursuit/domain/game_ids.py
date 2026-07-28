"""Game identifiers and the four standardized artifact names (book Appendix F #3)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime


def new_game_uid() -> str:
    return uuid.uuid4().hex[:12]


def make_game_id(group_a: str, group_b: str, when: datetime | None = None) -> str:
    ts = (when or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9-]", "-", f"{group_a}-vs-{group_b}")
    return f"{slug}-{ts}"


def declaration_name(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def config_name(game_id: str, sub_game: int) -> str:
    return f"config_{game_id}_g{sub_game:02d}.json"


def log_name(game_id: str, sub_game: int) -> str:
    return f"log_{game_id}_g{sub_game:02d}.json"


def result_name(game_id: str) -> str:
    return f"result_{game_id}.json"
