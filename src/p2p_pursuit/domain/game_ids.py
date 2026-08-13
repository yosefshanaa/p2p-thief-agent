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


def reference_game_id(group_a: str, group_b: str) -> str:
    """The reference family's id: the two group slugs, lexicographically ordered.

    Ours carries a timestamp and is minted before the opponent's slug is known,
    which is harmless until it becomes the first key of a *mutual* signature -
    two peers cannot agree on a string one of them stamped with its own clock.
    """
    lo, hi = sorted((group_a, group_b))
    return f"{lo}-vs-{hi}"


def reference_game_uid(terms: dict, group_a: str, group_b: str) -> str:
    """Their deterministic uid: a UUID over the agreed terms and both slugs.

    Deterministic on purpose - both sides derive it independently and must land
    on the same value, so a uid carried over from an earlier pairing shows up as
    a mismatch instead of quietly labelling this series with the last one's id.
    """
    from .crypto import canonical_bytes, sha256_raw

    lo, hi = sorted((group_a, group_b))
    material = canonical_bytes(terms) + b"|" + lo.encode("utf-8") + b"|" + hi.encode("utf-8")
    return str(uuid.UUID(bytes=sha256_raw(material)[:16]))


def declaration_name(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def config_name(game_id: str, sub_game: int) -> str:
    return f"config_{game_id}_g{sub_game:02d}.json"


def log_name(game_id: str, sub_game: int) -> str:
    return f"log_{game_id}_g{sub_game:02d}.json"


def result_name(game_id: str) -> str:
    return f"result_{game_id}.json"
