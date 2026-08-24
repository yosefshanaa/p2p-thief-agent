"""MaRs-777's `result_agreement`: the two-way core both teams must hash alike.

Their `PEER_RESULT_AGREEMENT_EXTENSION.md` §5. A third cross-team digest, and a
third set of rules - it is neither :mod:`.mutual_signature` nor :mod:`.consensus`
and is never aliased to either:

============  ==============================  =================================
              series consensus                 result agreement (this module)
============  ==============================  =================================
carried on    ``submit_audit`` envelope        ``receive_control``, kind
                                               ``result_agreement``
answer        ``{"ok": true}``                 a **bare 64-hex string**
scope         one side's view of six rows      BOTH sides' contributions merged
============  ==============================  =================================

Without it their peer never finalizes: no ``result_sha256``, no
``mutual_agreement``, the official set never reaches fourteen, and Appendix E
rule 35 scores a missing report 0 for **both** groups. So a wrong digest here is
not a lost confirmation - it is the whole counted fixture, for both teams.

Four readings of their §5 are ours rather than theirs, because the document
states them ambiguously. All four are isolated in this module and marked
``AMBIGUOUS`` so a golden vector can settle them in one edit:

1. the slot **keys** are the literal strings ``group_a``/``group_b``, and only
   the *assignment* follows code-point order (`_SLOTS`);
2. ``github_links`` members are the literal ``group_a_police`` family, not
   ``<gid>_police`` (:func:`_github_links`);
3. ``cumulative.series_outcome`` uses the role vocabulary its siblings
   ``cop_total``/``thief_total`` are keyed by (:func:`_cumulative`);
4. ``cop_score``/``thief_score`` stay **role**-keyed inside a row even though
   ``github_commit`` and ``tokens`` beside them are slot-keyed (:func:`_row`).

Reading 1 is the load-bearing one and the argument for it is reading 2: their
``github_links`` spells composite *literal* names, which only parses if the slot
names are fixed strings and the ordering decides which team lands in which.
"""

from __future__ import annotations

from typing import Any

from ..domain.crypto import canonical_bytes, sha256_hex

__all__ = ["APPROVAL_KIND", "OUTCOMES", "SLOT_A", "SLOT_B", "approval_core",
           "contribution", "contribution_entries", "result_sha256", "slots",
           "window_tokens"]

#: Their `receive_control` discriminator. Every other kind keeps its old answer.
APPROVAL_KIND = "result_agreement"

#: AMBIGUOUS (1). Literal slot names; the ordering below decides who is which.
SLOT_A, SLOT_B = "group_a", "group_b"

#: Their §5: `tie` is explicitly NOT a sub-game outcome.
OUTCOMES = frozenset({"capture", "survival", "technical_loss"})

#: Ours maps onto theirs. `timeout` is our alias for a step-limit survival and
#: has no place here - their §11 files survival, never timeout - so it is mapped
#: rather than passed through, and anything unknown raises.
OUTCOME_ALIASES = {"timeout": "survival", "tamper_forfeit": "technical_loss"}


def slots(group_a: str, group_b: str) -> dict[str, str]:
    """Slot name -> group id, by ascending Unicode code point of the id.

    Both peers must agree without exchanging it, which is the whole point of
    deriving it from the ids rather than from who proposed.
    """
    lo, hi = sorted((group_a, group_b))
    return {SLOT_A: lo, SLOT_B: hi}


def _slot_of(gid: str, table: dict[str, str]) -> str:
    for slot, holder in table.items():
        if holder == gid:
            return slot
    raise ValueError(f"{gid!r} holds no slot in {table}")


def window_tokens(cumulative: list[int]) -> list[int]:
    """Per-window usage from our running series total, as differences.

    Our engine keeps one counter for the whole series and each sub-game log
    records its value at that boundary, so window n cost (total_n - total_n-1).
    Never negative: a counter that went backwards is a bug we would rather see
    as a zero than as a digest nobody can reproduce.
    """
    out, previous = [], 0
    for total in cumulative:
        out.append(max(0, int(total) - previous))
        previous = int(total)
    return out


def contribution_entries(rows: list[dict[str, Any]], *,
                         commits: dict[int, str],
                         tokens: dict[int, int]) -> list[dict[str, Any]]:
    """Our own six entries: ascending, each index exactly once, never padded.

    Their §4 forbids sorting, deduplicating or padding on the *receiving* side,
    so the shaping has to be right where it is built. A missing window is an
    error here rather than a hole discovered inside their validator.
    """
    entries = []
    for row in sorted(rows, key=lambda r: r["index"]):
        n = row["index"]
        if n not in commits:
            raise ValueError(f"no commit declared for sub-game {n}")
        entries.append({"sub_game": n, "github_commit": commits[n],
                        "tokens": int(tokens.get(n, 0))})
    seen = [e["sub_game"] for e in entries]
    if len(set(seen)) != len(seen):
        raise ValueError(f"repeated sub_game in contribution: {seen}")
    return entries


def contribution(*, group_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"group_id": group_id, "entries": entries}


def _github_links(table: dict[str, str], repos: dict[str, dict[str, str]]
                  ) -> dict[str, str]:
    """AMBIGUOUS (2). Literal `group_a_police` names, four of them.

    Our own repo dict is keyed `cop`/`thief`; theirs is `police`/`thief`. The
    wire word is **police** - the same trap as the signed `roles` key - so the
    lookup accepts either spelling and emits neither.
    """
    links = {}
    for slot, gid in table.items():
        mine = repos.get(gid) or {}
        links[f"{slot}_police"] = mine.get("police") or mine.get("cop") or ""
        links[f"{slot}_thief"] = mine.get("thief") or ""
    return links


def _row(row: dict[str, Any], *, table: dict[str, str],
         commits: dict[str, str], tokens: dict[str, int]) -> dict[str, Any]:
    """One sub-game. AMBIGUOUS (4): scores stay role-keyed, beside slot-keyed
    commits and tokens - their §5 lists them that way and we mirror it rather
    than "fixing" it into something they will not reproduce."""
    ending = row.get("ending")
    outcome = OUTCOME_ALIASES.get(ending, ending)
    if outcome not in OUTCOMES:
        raise ValueError(f"sub-game {row.get('index')}: {ending!r} is not an "
                         f"outcome ({sorted(OUTCOMES)}; `tie` is not one)")
    return {
        "sub_game": row["index"],
        "cop_score": row["cop_score"],
        "thief_score": row["thief_score"],
        "outcome": outcome,
        "github_commit": {slot: commits.get(slot, "") for slot in table},
        "tokens": {slot: int(tokens.get(slot, 0)) for slot in table},
    }


#: Their `series_outcome` vocabulary, settled by the 17:36 vector. It is the
#: ROLE that took more points across the series, never a group id - and the
#: pursuer is spelled **"cop"** here, not "police". That is the opposite of the
#: signed `roles` key in `mutual_signature`, where the wire word is "police" and
#: "cop" is wrong. Two cross-team digests, two spellings of the same role, and
#: nothing on the wire to catch a swap: it costs a digest, silently, in whichever
#: direction you get it backwards.
SERIES_OUTCOMES = ("cop", "thief", "tie")


def _cumulative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Series role totals. `cop_total` and `thief_total` are role totals, not
    team totals - under alternation neither names a team - so the outcome beside
    them is read the same way: which ROLE out-scored the other."""
    cop = sum(r["cop_score"] for r in rows)
    thief = sum(r["thief_score"] for r in rows)
    outcome = "tie" if cop == thief else ("cop" if cop > thief else "thief")
    return {"cop_total": cop, "thief_total": thief, "series_outcome": outcome}


def approval_core(*, game_id: str, game_uid: str, declaration_ref: str,
                  timestamp: str, rows: list[dict[str, Any]],
                  contributions: dict[str, list[dict[str, Any]]],
                  repos: dict[str, dict[str, str]],
                  group_a: str, group_b: str) -> dict[str, Any]:
    """`RESULT_APPROVAL_CORE` - both contributions merged onto the settled rows.

    ``contributions`` is keyed by group id, each holding that team's six entries.
    Scores and outcomes are **jointly derived** from our settled rows and never
    contributed by either side; only commits and tokens come from the wire.

    ``result_sha256``, ``mutual_agreement`` and ``reported_by`` are excluded by
    their §5 - a digest may not sit inside the bytes it covers.
    """
    table = slots(group_a, group_b)
    by_slot_commit: dict[int, dict[str, str]] = {}
    by_slot_tokens: dict[int, dict[str, int]] = {}
    for gid, entries in contributions.items():
        slot = _slot_of(gid, table)
        for entry in entries:
            n = int(entry["sub_game"])
            by_slot_commit.setdefault(n, {})[slot] = entry["github_commit"]
            by_slot_tokens.setdefault(n, {})[slot] = int(entry["tokens"])
    ordered = sorted(rows, key=lambda r: r["index"])
    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "declaration_ref": declaration_ref,
        "teams": {slot: {"group_id": gid} for slot, gid in table.items()},
        "github_links": _github_links(table, repos),
        "sub_games": [_row(row, table=table,
                           commits=by_slot_commit.get(row["index"], {}),
                           tokens=by_slot_tokens.get(row["index"], {}))
                      for row in ordered],
        "cumulative": _cumulative(ordered),
        "total_tokens": {
            slot: sum(int(e["tokens"]) for e in contributions.get(gid, []))
            for slot, gid in table.items()},
        "timestamp": timestamp,
    }


def result_sha256(core: dict[str, Any]) -> str:
    """Their §5 digest: compact canonical bytes, sorted keys, ensure_ascii=False."""
    return sha256_hex(canonical_bytes(core))


class NotReadyError(RuntimeError):
    """Our own six entries are not assembled yet - explicitly retryable.

    Their §6: a valid request may arrive early, because both peers finish
    sub-game six at different moments and the proposer sends the instant its own
    settlement completes. The receiver waits boundedly and then processes the
    *same* request; on timeout it refuses retryably and **mutates nothing**.
    Raised rather than answered with a digest built from a half-finished series,
    which would be a wrong-but-plausible 64-hex string - the one failure mode
    this whole exchange exists to prevent.
    """


# Step-0 and its HMAC proof live in `.step0`; re-exported so the many importers
# of this module keep one import surface for the whole agreement protocol.
from .step0 import (  # noqa: E402
    AUTH_PROFILE,
    CTX_RESULT,
    CTX_STEP0,
    auth_block,
    hmac_proof,
    step0_core,
    step0_declaration,
)

__all__ = [
    "APPROVAL_KIND", "AUTH_PROFILE", "CTX_RESULT", "CTX_STEP0", "OUTCOMES",
    "OUTCOME_ALIASES", "SERIES_OUTCOMES", "NotReadyError", "approval_core",
    "auth_block", "contribution", "contribution_entries", "hmac_proof",
    "result_sha256", "slots", "step0_core", "step0_declaration", "window_tokens",
]
