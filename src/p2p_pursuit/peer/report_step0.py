"""Sending the Step-0 declaration before a ball is kicked.

Split out of :mod:`.runtime_reports` (§3.2). One concern: minting the Step-0
core from the agreed terms, signing it, and getting it accepted - the message
whose freshness window and equality check an opponent may disagree about.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from ..shared import sysinfo
from ..shared.version import CODE_VERSION
from .report_consensus import _their_group_id


def send_step0(rt: Any, log_fn: Any) -> dict[str, Any] | None:
    """Push our authenticated Step-0 before the series, on `negotiate`'s other shape.

    Sent BEFORE the first window rather than as counted-run-up paperwork, because
    on MaRs-777's wire it is load-bearing for the series itself: their backend
    publishes a per-sub-game contribution entry that requires a merged Step-0
    declaration, and does so at every window boundary. Missing, their police
    backend crashes at `contribution.publish(...)` after playing window 1, never
    reaches `settled(1)`, and their gateway then holds our next greeting open
    against an 1800 s bound while we time out against it forever. That is not a
    hypothesis - it is what killed the 2026-08-24 friendly at window 2.

    `auth` is REQUIRED and has no default on their wire, so a Step-0 without it
    is refused at input validation with a missing-field error - which by the
    reasoning above is the crash we moved this early to avoid. Without a
    configured secret we therefore send nothing at all rather than something
    certain to be refused, and say so once.

    The proof covers a 19-member projection, not this whole document: see
    `result_agreement.step0_core` for the two places the projection and the wire
    disagree about the same field.
    """
    from ..report.result_agreement import (
        CTX_STEP0,
        auth_block,
        slots,
        step0_core,
        step0_declaration,
    )
    from ..shared.config_env import hmac_secret

    step0 = getattr(rt.link, "step0", None)
    if not callable(step0):
        return None
    secret = hmac_secret()
    key_id = (os.environ.get("P2P_HMAC_KEY_ID") or "").strip()
    if not secret or not key_id:
        log_fn(f"[{rt.role}] Step-0 needs P2P_HMAC_SECRET and P2P_HMAC_KEY_ID; "
               f"not sending an unauthenticated one (it would be refused)")
        return None
    my_gid = rt.peer.group_id or "us"
    their_gid = _their_group_id(rt)
    slot = next(s for s, gid in slots(my_gid, their_gid).items() if gid == my_gid)
    doors = dict(rt.peer.public_doors or {})
    subtree = step0_declaration(
        group_id=my_gid, group_name=rt.peer.group_name,
        members=list(rt.peer.members), repos=dict(rt.peer.repos),
        mcp_endpoint=doors.get("cop") or doors.get("thief")
        or f"http://0.0.0.0:{rt.peer.my_port}/mcp",
        llm_model=rt.peer.llm_model, code_version=CODE_VERSION,
        commit=sysinfo.git_commit(), spec=sysinfo.collect())
    budget = rt.shared.network.get("token_budget_per_series", 200000)
    # The agreed constant, not a stamp. Their runtime compares game_start by
    # exact equality against the value in their launch document, so a clock
    # reading can never match it - E-CONFIG-MISMATCH, 2026-08-24. It is one of
    # the 19 members of the Step-0 core, so setting it re-signs the core: the
    # HMAC is computed below, after this value is in. Not a deadline - the
    # agreed instant may already have passed and that changes nothing; what
    # matters is that both declarations carry the same constant.
    start = ((os.environ.get("P2P_GAME_START") or "").strip()
             or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    declaration = {
        "game_id": rt.game_id, "game_uid": rt.game_uid,
        "teams": {slot: subtree}, "times": {"game_start": start},
        "token_budget_per_series": int(budget)}
    core = step0_core(game_id=rt.game_id, game_uid=rt.game_uid, game_start=start,
                      slot=slot, declaration=subtree,
                      token_budget_per_series=budget)
    envelope = {"declaration": declaration,
                "auth": auth_block(secret, CTX_STEP0, core, key_id=key_id)}
    try:
        answer = rt.deadline.call(step0, envelope)
        log_fn(f"[{rt.role}] Step-0 accepted (slot {slot}, key {key_id}): {answer}")
        return declaration
    except Exception as exc:  # noqa: BLE001 - a peer without Step-0 is not an error
        log_fn(f"[{rt.role}] Step-0 not accepted ({exc}); continuing without it")
        return None
