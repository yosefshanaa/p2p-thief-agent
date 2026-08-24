"""The result-agreement exchange: our six entries, theirs, and the signed core.

Split out of :mod:`.runtime_reports` (§3.2). One concern: reaching a result
both sides signed, under a bound - a request that waits forever holds one of
their threads and still answers nothing.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

from ..domain import game_ids
from ..shared import sysinfo
from .report_consensus import _their_group_id

#: How long a `result_agreement` request may wait for our own six entries to
#: assemble before we refuse it retryably (their §6). Bounded by design: a
#: request that waits forever holds one of their threads and still answers
#: nothing, and their own bound is the agreed watchdog.
APPROVAL_READY_WAIT = 120.0
APPROVAL_POLL = 0.5


def _our_contribution(rt: Any) -> list[dict[str, Any]]:
    """Our six entries: our declared commit and our own metered tokens.

    Both halves are ours alone by their §4 - never inferred, never supplied on
    the other side's behalf. Our commit is a single value across all six rows
    because we run ONE process: the two repos are a submission split of one
    workspace, not two agents. Their §7 accepts that (it checks the entry against
    what the contributor declared, not that the two roles differ), and their
    Step-0 wire still wants `github_commits` as an object, so the same hex goes
    in both slots there.
    """
    from ..report.result_agreement import contribution_entries, window_tokens

    rows = sorted(rt.sub_results, key=lambda r: r["index"])
    per_window = window_tokens([r.get("tokens_cumulative", 0) for r in rows])
    commit = sysinfo.git_commit()
    return contribution_entries(
        rows,
        commits={r["index"]: r.get("github_commit") or commit for r in rows},
        tokens=dict(zip([r["index"] for r in rows], per_window, strict=True)))


def runtime_result_agreement(rt: Any, payload: dict[str, Any], *,
                             their_gid: str, entries: list[dict[str, Any]]) -> str:
    """Assemble `RESULT_APPROVAL_CORE` from both contributions; return its digest.

    The timestamp is **the proposer's, adopted verbatim** and never regenerated
    or reformatted - MaRs-777 enforce that on their side and fail closed on a
    re-stamped echo, and two peers stamping their own clocks could never agree
    on a document that carries one.

    Scores and outcomes come from our own settled rows, never from the wire:
    their §5 says both sides derive them jointly from the settled sub-game and
    the locked scoring table. Only commits and tokens are contributed.
    """
    from ..report.result_agreement import NotReadyError, approval_core, result_sha256

    expected = rt.num_games
    deadline = time.monotonic() + APPROVAL_READY_WAIT
    while len(rt.sub_results) < expected:
        if time.monotonic() >= deadline:
            raise NotReadyError(
                f"{len(rt.sub_results)} of {expected} sub-games settled after "
                f"{APPROVAL_READY_WAIT:g}s")
        time.sleep(APPROVAL_POLL)
    if not their_gid:
        raise ValueError("contribution carries no group_id")
    if len(entries) != expected:
        raise ValueError(f"contribution has {len(entries)} entries, expected {expected}")
    my_gid = rt.peer.group_id or "us"
    theirs = (rt.service.their_handshake or {}).get("repos") or {}
    return result_sha256(approval_core(
        game_id=rt.game_id, game_uid=rt.game_uid,
        declaration_ref=game_ids.declaration_name(rt.game_id),
        timestamp=payload.get("timestamp") or "",
        rows=rt.sub_results,
        contributions={my_gid: _our_contribution(rt), their_gid: list(entries)},
        repos={my_gid: dict(rt.peer.repos), their_gid: dict(theirs)},
        group_a=my_gid, group_b=their_gid))


def _we_propose(my_gid: str, their_gid: str) -> bool:
    """Their §3: the byte-wise lower ``group_id`` proposes. Never negotiated.

    Deterministic on both sides so neither has to be told, and so two peers can
    never both wait for the other's request. ``MaRs-777`` < ``ahk-yosi`` by code
    point, so against them we are the receiver and answer first.
    """
    return my_gid < their_gid


def exchange_result_agreement(rt: Any, log_fn: Any) -> dict[str, Any]:
    """The second direction: send our own request and compare the two digests.

    Their §3 is one request each, and **both must complete** - "a side that only
    sends has agreed nothing". We answer theirs on `receive_control`; this is the
    half that makes our own agreement real.

    The timestamp is the proposer's. When they propose we echo the value we
    already adopted while answering; when we propose we mint one and they echo
    it. Either way exactly one clock is read, which is what makes a document
    carrying a timestamp reproducible at all.

    Never raises: a failed agreement is recorded as a fact. Their §7 files the
    same way - "no agreement; the result stays unreportable, and that is
    recorded honestly" - and an exception here would discard six played windows.
    """
    from ..report.result_agreement import APPROVAL_KIND, CTX_RESULT, auth_block, contribution
    from ..shared.config_env import hmac_secret

    my_gid = rt.peer.group_id or "us"
    their_gid = _their_group_id(rt)
    block: dict[str, Any] = {"sent": False, "our_sha": None, "their_sha": None,
                             "sha_match": False, "agreed": False,
                             "timestamp": None, "proposer": None}
    bridge = rt.bridge
    if bridge is None:
        log_fn(f"[{rt.role}] result agreement needs the reference dialect; skipped")
        return block
    we_propose = _we_propose(my_gid, their_gid)
    block["proposer"] = my_gid if we_propose else their_gid
    stamp = getattr(bridge, "approval_timestamp", None)
    if not stamp:
        if not we_propose:
            # Their request never arrived, so there is nothing to echo and
            # nothing they could compare ours against. Minting our own here
            # would guarantee two different cores.
            log_fn(f"[{rt.role}] no result-agreement request arrived from "
                   f"{their_gid} (they propose); nothing to answer or echo")
            return block
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    block["timestamp"] = stamp
    try:
        entries = _our_contribution(rt)
        ours = runtime_result_agreement(
            rt, {"timestamp": stamp}, their_gid=their_gid,
            entries=_their_entries(rt, their_gid))
    except Exception as exc:  # noqa: BLE001 - recorded, never fatal
        log_fn(f"[{rt.role}] cannot assemble the approval core: {exc}")
        return block
    block["our_sha"] = ours
    payload = {
        "game_id": rt.game_id, "game_uid": rt.game_uid,
        "declaration_ref": game_ids.declaration_name(rt.game_id),
        "timestamp": stamp,
        "contribution": contribution(group_id=my_gid, entries=entries)}
    request = {"kind": APPROVAL_KIND, "payload": payload}
    # Our client opens a session per call, so the identity their Step-0 bound to
    # a session is gone by the time this lands. Their fresh-session verifier
    # takes a proof on the request instead - `auth` BESIDE `payload`, never
    # inside it, so RESULT_APPROVAL_CORE and its digest are untouched. Optional
    # for a peer that holds one session; required for us, so always sent.
    secret = hmac_secret()
    key_id = (os.environ.get("P2P_HMAC_KEY_ID") or "").strip()
    if not secret or not key_id:
        # Their fresh-session verifier *requires* the proof on the request, so an
        # unsigned one is a certain E-AUTH-FAILURE - arriving after all six
        # windows have been played, and reading as a remote rejection rather than
        # as our own missing variable. Refuse it here exactly as `send_step0`
        # refuses, and record the refusal as the fact it is.
        log_fn(f"[{rt.role}] result agreement needs P2P_HMAC_SECRET and "
               f"P2P_HMAC_KEY_ID; not sending an unauthenticated request "
               f"(it would be refused)")
        return block
    request["auth"] = auth_block(secret, CTX_RESULT, payload, key_id=key_id)
    try:
        answer = rt.deadline.call(rt.link.receive_control, request)
        block["sent"] = True
    except Exception as exc:  # noqa: BLE001
        log_fn(f"[{rt.role}] result-agreement request failed: {exc}")
        return block
    theirs = answer if isinstance(answer, str) else (answer or {}).get("result_sha256")
    block["their_sha"] = theirs
    block["sha_match"] = bool(theirs) and theirs == ours
    block["agreed"] = block["sent"] and block["sha_match"]
    log_fn(f"[{rt.role}] result agreement ours={ours[:12]}… "
           f"theirs={(theirs or 'none')[:12]}… agreed={block['agreed']}")
    if theirs and not block["sha_match"]:
        log_fn(f"[{rt.role}] DIGESTS DIFFER - no agreement. Neither side may "
               f"file this as mutually agreed; the cause is in the core, not "
               f"the transport.")
    return block


def _their_entries(rt: Any, their_gid: str) -> list[dict[str, Any]]:
    """Their six entries as they contributed them, retained when we answered.

    Both directions hash the SAME core, so ours must be built from the entries
    they actually sent - not from anything we could derive. If their request has
    not arrived we cannot build the core at all, and saying so is the honest
    outcome: inventing their commits or their token counts would produce a
    plausible digest that agrees with nobody.
    """
    entries = getattr(rt.bridge, "approval_their_entries", None)
    if not entries:
        raise ValueError(f"no contribution received from {their_gid}")
    return list(entries)
