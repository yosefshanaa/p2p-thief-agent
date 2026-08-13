"""The reference family's *mutual* result signature (their wire contract §7).

Both peers file their own result artifact, and the two must agree. Rather than
diff whole documents - which legitimately differ in clocks, token counts and
each side's private audit verdicts - the family hashes a **projection**: the
game id, five aggregate fields, and exactly five fields per sub-game row. Rows
may carry anything else without disturbing the digest, which is what lets two
independent implementations agree without sharing a schema.

Two traps live here, and both are theirs by specification rather than ours by
choice:

* **The encoding is not the commitment encoding.** Commitments use compact
  separators; this signature uses ``json.dumps`` *defaults* (``", "`` / ``": "``).
  Same document, different bytes, different hash - see :func:`~..domain.crypto.spaced_bytes`.
* **Scores and roles are keyed by group id, not by role.** Under role
  alternation a peer is police on some sub-games and thief on others, so a
  role-keyed total cannot be compared between two teams at all.
"""

from __future__ import annotations

from typing import Any

from ..domain.crypto import sha256_hex, spaced_bytes
from ..domain.rules import POLICE, THIEF

__all__ = ["AGGREGATE_KEYS", "SUB_GAME_KEYS", "mutual_signature", "signature_document",
           "signed_aggregate", "signed_row_fields"]

#: The pursuer's spelling inside `roles`, which is a *signed* key: one spelling
#: apiece means two teams that agree on everything still hash differently, on
#: every row. It is **"police"**, not "cop" - confirmed by uoh-sqak 2026-08-09.
#: "cop" survives only in `cop_start` and `repos.cop`, both of which are terms
#: and links rather than signed row values, which is exactly what makes the trap
#: invisible: the word is all over the protocol and never in this field.
THEIR_ROLE_NAME = {POLICE: POLICE, THIEF: THIEF}

#: Their `result` vocabulary. Only "capture" and "survival" score; everything
#: else is 0-0 for both teams by construction on their side. Ours is the same
#: set plus `technical_loss`, which has no meaning to them - so it is mapped to
#: the closest term they *do* file rather than left to differ on a signed key.
RESULT_ALIASES = {"technical_loss": "timeout"}

#: The only per-row keys that reach the digest.
SUB_GAME_KEYS = ("sub_game_number", "roles", "result", "winner_group", "score")
#: The only aggregate keys that reach the digest.
AGGREGATE_KEYS = ("total_score", "sub_games_won", "ties", "winner_group", "series_tie")


def _project(row: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    """Keep exactly ``keys``, absent ones as ``None``.

    A missing key must become an explicit ``None`` rather than vanish: two peers
    disagreeing about whether a field exists would otherwise hash differently
    while looking identical in a side-by-side read.
    """
    source = row if isinstance(row, dict) else {}
    return {key: source.get(key) for key in keys}


def signature_document(result: dict[str, Any]) -> dict[str, Any]:
    """Reduce a full result artifact to the three-part document that is signed."""
    rows = result.get("sub_games") or []
    return {
        "game_id": result.get("game_id"),
        "aggregate": _project(result.get("aggregate"), AGGREGATE_KEYS),
        "sub_games": [_project(row, SUB_GAME_KEYS) for row in rows],
    }


def mutual_signature(result: dict[str, Any]) -> str:
    """The hex digest both teams must produce from their own artifact."""
    return sha256_hex(spaced_bytes(signature_document(result)))


def signed_row_fields(row: dict[str, Any], *, my_group: str, their_group: str,
                      my_role: str) -> dict[str, Any]:
    """The five signed keys for one of our sub-game rows, keyed by group.

    Our row is role-keyed (`cop_score` / `thief_score`) and names a *role* as the
    winner. Under role alternation neither survives comparison between two teams:
    "the police won" says nothing about which team that was on sub-game 4.
    """
    their_role = THIEF if my_role == POLICE else POLICE
    mine, mine_other = ("cop_score", "thief_score") if my_role == POLICE \
        else ("thief_score", "cop_score")
    winner = row.get("winner")
    winner_group = {my_role: my_group, their_role: their_group}.get(winner)
    return {
        "sub_game_number": row["index"],
        "roles": {my_group: THEIR_ROLE_NAME[my_role],
                  their_group: THEIR_ROLE_NAME[their_role]},
        "result": RESULT_ALIASES.get(row["ending"], row["ending"]),
        "winner_group": winner_group,
        "score": {my_group: row[mine], their_group: row[mine_other]},
    }


def signed_aggregate(rows: list[dict[str, Any]], *, my_group: str,
                     their_group: str) -> dict[str, Any]:
    """Series totals over rows that already carry :func:`signed_row_fields`.

    A sub-game with no winner counts as a tie, which is also how a technical
    loss with no surviving winner reads - deliberately, since neither team may
    claim it.
    """
    total = {my_group: 0, their_group: 0}
    won = {my_group: 0, their_group: 0}
    ties = 0
    for row in rows:
        for group, points in (row.get("score") or {}).items():
            total[group] = total.get(group, 0) + points
        winner = row.get("winner_group")
        if winner is None:
            ties += 1
        else:
            won[winner] = won.get(winner, 0) + 1
    series_tie = total[my_group] == total[their_group]
    return {
        "total_score": total,
        "sub_games_won": won,
        "ties": ties,
        "winner_group": None if series_tie else max(total, key=lambda g: total[g]),
        "series_tie": series_tie,
    }
