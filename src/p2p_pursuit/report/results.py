"""The mandatory signed result report (book ch. 9.3.3).

Machine-readable JSON, sent as an attachment by BOTH teams independently;
carries all four repo links, the per-sub-game github_commit and the total
token consumption (#33-35, #53-54).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..domain.audit import NOT_REPORTED_REFERENCE, VERIFIED_OK
from ..domain.crypto import digest
from ..domain.rules import POLICE
from ..shared.version import CODE_VERSION


def build_result(*, game_uid: str, game_id: str, my_group: dict[str, Any],
                 opp_group: dict[str, Any] | None, sub_games: list[dict[str, Any]],
                 police_total: int, thief_total: int, tie_score: int,
                 tokens_used: int, github_commit: str,
                 my_role: str, mutual_agreement: bool) -> dict[str, Any]:
    my_total = police_total if my_role == POLICE else thief_total
    opp_total = thief_total if my_role == POLICE else police_total
    if police_total == thief_total:
        series_winner, my_total, opp_total = "tie", tie_score, tie_score
    else:
        series_winner = POLICE if police_total > thief_total else "thief"
    body: dict[str, Any] = {
        "report_type": "game_result",
        "game_uid": game_uid,
        "game_id": game_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "timezone": "Asia/Jerusalem",
        "code_version": CODE_VERSION,
        "github_commit": github_commit,
        "groups": {"mine": my_group, "opponent": opp_group},
        "sub_games": sub_games,
        "totals": {"police": police_total, "thief": thief_total},
        "my_role": my_role,
        "my_total": my_total,
        "opponent_total": opp_total,
        "series_winner": series_winner,
        "tokens_used": tokens_used,
        "mutual_agreement": mutual_agreement,
    }
    body["result_sha256"] = digest(body)
    return body


def sub_game_row(*, index: int, ending: str, winner: str, cause: str,
                 police_score: int, thief_score: int, moves_played: int,
                 github_commit: str, audit_verdict: str,
                 opponent_audit: str = "not reported") -> dict[str, Any]:
    """One sub-game's scored outcome. Both audit directions are recorded: our
    verdict of their log, and the verdict they returned on ours."""
    return {
        "index": index, "ending": ending, "winner": winner, "cause": cause,
        "cop_score": police_score, "thief_score": thief_score,
        "moves_played": moves_played, "github_commit": github_commit,
        "audit": audit_verdict, "opponent_audit": opponent_audit,
    }


def agreement_reached(sub_games: list[dict[str, Any]]) -> bool:
    """True when every sub-game was audited clean and the exchange completed.

    "Audited clean" is our own verdict of their log, which is never waived. The
    opponent's verdict of *ours* is required too whenever the dialect can carry
    it - a returned failure, or silence where an answer was due, still means no
    agreement, and claiming otherwise would put an unverified assertion into a
    signed result.

    The one case that does not block is `NOT_REPORTED_REFERENCE`: the reference
    dialect's `submit_audit` answers `{"ok": True}` on both sides, so *neither*
    peer can report what it made of the other's log. Requiring it there made
    this flag unreachable by construction - measured against najamjad
    2026-08-21, a 6-0 series with `Verified OK` on all six windows filed
    `mutual_agreement: false` while their report of the same series said true.
    Two signed files contradicting each other on a field named
    `mutual_agreement` is precisely what rule 35 voids for, and the reports did
    not actually disagree about anything: their peer asserts "my audit passed
    and the exchange completed", which is the reading taken here.

    So this is a *negotiated* definition, not a relaxed one. It belongs in both
    terms documents, because a peer that reads it strictly and a peer that reads
    it this way will file opposite booleans on an identical series.
    """
    return bool(sub_games) and all(
        row.get("audit") == VERIFIED_OK
        and row.get("opponent_audit") in (VERIFIED_OK, NOT_REPORTED_REFERENCE)
        for row in sub_games)
