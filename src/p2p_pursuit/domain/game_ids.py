"""Game identifiers and the four standardized artifact names (book Appendix F #3)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

#: Stands in for an opponent that named no group. It is deliberately not a
#: slug either side could hold, because the derived ids are only shared when
#: both peers feed them the same two real slugs - see `_adopt_shared_ids`.
UNKNOWN_GROUP = "opponent"


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


def reference_game_uid(terms: dict, group_a: str, group_b: str,
                       game_id: str = "") -> str:
    """Their deterministic uid: a UUID over the agreed terms and both slugs.

    Deterministic on purpose - both sides derive it independently and must land
    on the same value, so a uid carried over from an earlier pairing shows up as
    a mismatch instead of quietly labelling this series with the last one's id.

    ``game_id`` folds a *mutually agreed label* in, replacing the slug pair in
    the seed. Two teams that label two series against each other `friendly-1`
    and `counted-1` otherwise derive one uid for both, because the label reaches
    the id and never the uid - which is the collision this closes. It is passed
    only when a label was actually negotiated: with it empty the seed is
    byte-identical to the unlabelled rule, so every peer we have already played
    keeps the uid it agreed with us. yanell11 pin the labelled form in their own
    unit tests and we verified both readings against them before adopting it.
    """
    from .crypto import canonical_bytes, sha256_raw

    lo, hi = sorted((group_a, group_b))
    tail = game_id.encode("utf-8") if game_id else \
        lo.encode("utf-8") + b"|" + hi.encode("utf-8")
    material = canonical_bytes(terms) + b"|" + tail
    return str(uuid.UUID(bytes=sha256_raw(material)[:16]))


def declaration_name(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def config_name(game_id: str, sub_game: int) -> str:
    return f"config_{game_id}_g{sub_game:02d}.json"


def log_name(game_id: str, sub_game: int) -> str:
    return f"log_{game_id}_g{sub_game:02d}.json"


def result_name(game_id: str) -> str:
    return f"result_{game_id}.json"
