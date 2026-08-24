"""Runtime reporting side: declaration, per-sub-game audit + artifacts, result, email."""

from __future__ import annotations

import contextlib
import os
import time
from datetime import UTC, datetime
from typing import Any

from ..domain import declarations, game_ids, negotiation
from ..domain.audit import VERIFIED_OK
from ..domain.crypto import digest
from ..domain.scoring import TECHNICAL_LOSS
from ..infra.email_sender import send_report
from ..report import artifacts, consensus, mutual_signature, results
from ..shared import sysinfo
from ..shared.gatekeeper import Gatekeeper
from ..shared.version import CODE_VERSION
from . import audit_bridge, log_manager
from .deadline import DeadlineExpiredError


def write_declaration(rt: Any, theirs: dict[str, Any]) -> None:
    me = declarations.team_block(
        group_id=rt.peer.group_id, group_name=rt.peer.group_name,
        members=rt.peer.members, repos=rt.peer.repos,
        mcp_url=f"http://0.0.0.0:{rt.peer.my_port}/mcp",
        llm_model=rt.peer.llm_model)
    opp = {k: theirs.get(k) for k in
           ("group_id", "group_name", "members", "repos", "code_version")}
    decl = declarations.build_declaration(
        game_uid=rt.game_uid, game_id=rt.game_id,
        game_number=rt.service.my_handshake["prior_counted_games"] + 1,
        config_sha256=rt.shared.sha256,
        scent_model_sha256=negotiation.scent_model_sha256(rt.peer.scent_model),
        token_cap=rt.shared.network.get("token_budget_per_series", 200000),
        me=me, opponent=opp)
    rt.declaration = decl
    artifacts.write_declaration(rt.out_dir, rt.game_id, decl)


def close_declaration(rt: Any) -> dict[str, Any] | None:
    """Stamp the series' finish time onto the declaration and rewrite it.

    Runs after the last sub-game and the consensus exchange, so `ended_at` is
    the end of the match rather than the end of the reporting. Best effort: a
    declaration that cannot be re-sealed must not discard a played series.
    """
    decl = getattr(rt, "declaration", None)
    if not decl:
        return None
    rt.declaration = declarations.close_declaration(decl)
    artifacts.write_declaration(rt.out_dir, rt.game_id, rt.declaration)
    return rt.declaration


#: A reference-derived peer negotiates the next sub-game the instant it finishes
#: the last one, and waits only ~60 s for our agreement. Our own audit wait sits
#: directly in front of that re-handshake, so a generous one does not merely
#: delay us - it blows their window and costs the whole next sub-game
#: ("Opponent never sent its agreement", measured live 2026-08-01). When we are
#: re-handshaking per sub-game, waiting longer than this can only lose ground:
#: their audit is already sent by then or it is not coming.
REHANDSHAKE_AUDIT_WAIT = 20.0


def _audit_wait(rt: Any) -> float:
    """How long to wait for their audit before moving to the next sub-game."""
    generous = rt.deadline.timeout_sec * 2
    if rt.peer.handshake_per_sub_game:
        return min(generous, REHANDSHAKE_AUDIT_WAIT)
    return generous


def finish_sub_game(rt: Any, n: int, log_fn) -> dict[str, Any]:
    """Mutual audit, log artifact and score row for one finished sub-game."""
    engine = rt.engine
    # Frozen at the moment sub-game n ended, and stamped with n. Both halves
    # matter: the running engine's records are emptied at the boundary, and a
    # package that does not name its index can only be filed by arrival time.
    package = audit_bridge.audit_package(engine, n)
    their_view = {"verdict": "not received", "violations": []}
    with contextlib.suppress(DeadlineExpiredError):
        their_view = rt.deadline.call(rt.link.audit, package)
    got = rt.service.wait_for_audit(n, _audit_wait(rt))
    my_verdict = rt.service.audit_verdicts.get(
        n, {"verdict": "no package received", "violations": []})
    opp_records = rt.service.audit_packages.get(n, {}).get("records", [])
    ending = engine.end.ending if engine.end else TECHNICAL_LOSS
    winner = engine.end.winner if engine.end else "none"
    cause = engine.end.cause if engine.end else "unknown"
    if got and my_verdict["verdict"] != "Verified OK":
        ending, winner = TECHNICAL_LOSS, engine.role
        cause = f"opponent log {my_verdict['verdict']}"
    p_score, t_score = engine.score_table.score(ending)
    audit_blob = {"mine_of_them": my_verdict, "theirs_of_us": their_view,
                  "my_reveal_binds": _reveal_self_check(rt, n)}
    log = log_manager.build_log(engine, opp_records, game_uid=rt.game_uid,
                                game_id=rt.game_id, audit=audit_blob, package=package)
    log_manager.write_log(log, rt.out_dir)
    artifacts.write_config_copy(rt.out_dir, rt.game_id, n, rt.shared.raw, rt.game_uid)
    row = results.sub_game_row(
        index=n, ending=ending, winner=winner, cause=cause,
        police_score=p_score, thief_score=t_score,
        moves_played=engine.my_steps if engine.role == "thief" else engine.opp_steps,
        github_commit=sysinfo.git_commit(), audit_verdict=my_verdict["verdict"],
        opponent_audit=their_view["verdict"])
    # The group-keyed projection a reference-family peer signs. Added to our own
    # row rather than replacing it: their contract says a row may carry anything
    # else, and our role-keyed fields are what our replay and audits read.
    row.update(mutual_signature.signed_row_fields(
        row, my_group=rt.peer.group_id or "us",
        their_group=_their_group_id(rt), my_role=engine.role))
    # The engine's counter is a running SERIES total, never reset at a boundary,
    # so this is cumulative-at-close and the per-window cost is the difference
    # from the previous row (`result_agreement.window_tokens`). Stored rather
    # than differenced here: the raw number is what our log already files, and a
    # difference computed twice from two places is a difference that can drift.
    row["tokens_cumulative"] = engine.tokens_used
    log_fn(f"[{rt.role}] sub-game {n}: {ending} winner={winner} ({cause}) "
           f"audit={my_verdict['verdict']}")
    return row


def _reveal_self_check(rt: Any, n: int) -> dict[str, Any]:
    """Our own verdict on our own reveal, filed next to theirs.

    We ask the opponent to prove every commitment they sent is revealed; the
    same claim about us belongs in our artifact, checked rather than asserted.
    """
    checks = getattr(rt.bridge, "reveal_self_checks", None)
    if checks is None or n not in checks:
        return {"verdict": "not applicable (native dialect)", "violations": []}
    violations = checks[n]
    return {"verdict": VERIFIED_OK if not violations else "BINDING FAILED",
            "violations": violations}


def _their_group_id(rt: Any) -> str:
    return (rt.service.their_handshake or {}).get("group_id") or "opponent"


def _push_consensus(rt: Any, bridge: Any, envelope: dict[str, Any],
                    log_fn: Any) -> tuple[str | None, bool]:
    """Deliver our envelope and collect theirs; return ``(their sha, delivered)``.

    Replaces a single attempt whose exception was suppressed. One unacknowledged
    shot is not a send: the two peers finish sub-game 6 at different moments, so
    ours could arrive while theirs is still assembling and be lost with nothing
    recorded on either side. What that produces is not a mismatch anybody can
    investigate - it is silence, which is indistinguishable from a peer that
    never speaks the protocol at all. MaRs-777 resend for their whole window and
    require a positive acknowledgement, and the hazard is symmetric.

    **Their digest arriving does not end our sending.** The two directions are
    independent: they can have settled and answered while our own envelope has
    never reached them, and stopping there would leave *them* unable to settle
    for the same reason we are protecting ourselves against. So the loop runs
    until both halves are done - ours acknowledged and theirs received - or the
    window closes.

    Both directions share one clock. We stop at ``consensus_wait_sec`` whether we
    are still retrying or merely listening, because the caller's contract is that
    this bounded wait costs the confirmation and never the series. Whatever has
    arrived by then is returned and recorded: a digest we received but could not
    answer is evidence, not something to discard.
    """
    retry = max(1.0, float(getattr(rt.peer, "consensus_retry_sec", 5)))
    deadline = time.monotonic() + rt.peer.consensus_wait_sec
    theirs: str | None = None
    acked, attempts = False, 0
    while True:
        if not acked:
            attempts += 1
            try:
                rt.deadline.call(bridge.submit_consensus, envelope)
                acked = True
                log_fn(f"[{rt.role}] consensus envelope delivered"
                       + ("" if attempts == 1 else f" on attempt {attempts}"))
            except Exception as exc:  # noqa: BLE001 - never fatal, by contract
                log_fn(f"[{rt.role}] consensus send attempt {attempts} failed "
                       f"({exc}); retrying every {retry:g}s")
        if acked and theirs is not None:
            return theirs, True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if not acked:
                log_fn(f"[{rt.role}] consensus envelope NEVER acknowledged in "
                       f"{attempts} attempts over {rt.peer.consensus_wait_sec}s "
                       f"- they cannot settle against us")
            elif theirs is None:
                log_fn(f"[{rt.role}] ours delivered, but no consensus envelope "
                       f"arrived within {rt.peer.consensus_wait_sec}s")
            return theirs, acked
        # Listening is also the retry pacer while we still need theirs; once we
        # have it, only the resend is left to time, and there is no second clock.
        slice_sec = min(retry, remaining)
        if theirs is None:
            theirs = bridge.wait_for_consensus(slice_sec)
        else:
            time.sleep(slice_sec)


def exchange_series_consensus(rt: Any, log_fn: Any) -> dict[str, Any]:
    """Send our series digest, wait briefly for theirs, and record both.

    Deliberately never raises. Agreement is *confirmed* by a received digest
    equal to ours, but a series that played and audited cleanly is still a
    played series: a tunnel that dies during this last round-trip must leave
    ``confirmed: false`` in the artifact, not an exception that discards six
    completed sub-games. Their §13 says the same from the other direction - a
    failed consensus is never repaired by re-running part of the old series.
    """
    projection = getattr(rt.peer, "consensus_projection", consensus.UID_PROJECTION)
    document, mine = consensus.projected_consensus(
        projection, game_id=rt.game_id, game_uid=rt.game_uid, rows=rt.sub_results,
        my_group=rt.peer.group_id or "us", their_group=_their_group_id(rt),
        # Appendix F's consolation, and only the projections that specify it ask
        # for it - see `mutual_signature.signed_aggregate`.
        tie_award=(rt.shared.scoring.get("tie_score", 2)
                   if projection == consensus.SIGNATURE_PROJECTION else 0))
    block: dict[str, Any] = {"document": document, "consensus_sha": mine,
                             "projection": projection,
                             "peer_consensus_sha": None, "sha_match": False,
                             "confirmed": False}
    bridge = rt.bridge
    if bridge is None:
        return block
    envelope = consensus.consensus_envelope(sender=rt.engine.role, sha=mine)
    theirs, delivered = _push_consensus(rt, bridge, envelope, log_fn)
    # Whether *they* can settle at all, which our own digest cannot tell us.
    block["envelope_delivered"] = delivered
    block["peer_consensus_sha"] = theirs
    block["sha_match"] = bool(theirs) and theirs == mine
    # Their §10.4: confirmed needs every peer log verified untampered, every
    # sub-game's result mutually agreed, AND a received digest equal to ours. A
    # local hash alone is never sufficient.
    #
    # Deliberately NOT `results.agreement_reached`, which additionally demands
    # the opponent's verdict *of us* - a value this dialect structurally never
    # returns (their `submit_audit` answers `{"ok": true}` and keeps its verdict
    # private), so requiring it would pin `confirmed` to false against every
    # reference peer, including one that agreed perfectly. Their clause (a) is
    # each side's own verdict of the log it received, which is `row["audit"]`;
    # clause (b) is subsumed by the digest, since the consensus object covers
    # every row's result, roles, score and winner.
    block["confirmed"] = bool(
        block["sha_match"]
        and all(row.get("audit") == VERIFIED_OK for row in rt.sub_results))
    log_fn(f"[{rt.role}] series consensus[{projection}] {mine[:12]}… peer="
           f"{(theirs or 'none')[:12]}… match={block['sha_match']} "
           f"confirmed={block['confirmed']}")
    return block


def build_result(rt: Any) -> dict[str, Any]:
    police_total = sum(r["cop_score"] for r in rt.sub_results)
    thief_total = sum(r["thief_score"] for r in rt.sub_results)
    theirs = rt.service.their_handshake or {}
    result = results.build_result(
        game_uid=rt.game_uid, game_id=rt.game_id,
        my_group={"group_id": rt.peer.group_id, "group_name": rt.peer.group_name,
                  "members": rt.peer.members, "repos": rt.peer.repos},
        opp_group={k: theirs.get(k) for k in
                   ("group_id", "group_name", "members", "repos")},
        sub_games=rt.sub_results, police_total=police_total, thief_total=thief_total,
        tie_score=rt.shared.scoring.get("tie_score", 2),
        tokens_used=rt.engine.tokens_used, github_commit=sysinfo.git_commit(),
        my_role=rt.role, mutual_agreement=results.agreement_reached(rt.sub_results))
    _attach_mutual_block(rt, result, theirs)
    artifacts.write_result(rt.out_dir, rt.game_id, result)
    return result


def _attach_mutual_block(rt: Any, result: dict[str, Any], theirs: dict[str, Any]) -> None:
    """The group-keyed aggregate, the cross-team fields, and the shared digest.

    Only `aggregate` and the per-row projection reach the signature; the rest
    must be right but is deliberately outside it, so an honest difference in
    clocks or token counts can never make two agreeing teams disagree.
    """
    my_gid = rt.peer.group_id or "us"
    their_gid = _their_group_id(rt)
    aggregate = mutual_signature.signed_aggregate(
        rt.sub_results, my_group=my_gid, their_group=their_gid)
    result["aggregate"] = aggregate
    result["links"] = _artifact_links(rt, my_gid, their_gid, theirs)
    # Truthful rule-#37 counters, each side's own number: ours from our config,
    # theirs off the identity they signed. Never invented on the other's behalf.
    result["games_played_including_this"] = {
        my_gid: rt.prior_counted_games + (1 if rt.counted else 0),
        their_gid: int(theirs.get("prior_counted_games") or 0) + (1 if rt.counted else 0),
    }
    # Book §9.2.2: the bonus rewards *winning* a first meeting, so a drawn
    # series awards it to nobody - and a friendly awards it to nobody at all.
    winner = aggregate["winner_group"]
    result["diversity_reward_applied"] = {
        group: bool(rt.counted and winner == group) for group in (my_gid, their_gid)}
    result["mutual_signature"] = mutual_signature.mutual_signature(result)
    if getattr(rt, "series_consensus", None) is not None:
        result["series_consensus"] = rt.series_consensus
    if getattr(rt, "result_agreement", None) is not None:
        result["result_agreement"] = rt.result_agreement
    # `build_result` sealed `result_sha256` over the body as it stood before
    # these fields existed. Recompute it, or our own integrity hash fails
    # against our own filed artifact - the same digest, over the same rule
    # (everything except the key itself).
    result.pop("result_sha256", None)
    result["result_sha256"] = digest(result)


def _artifact_links(rt: Any, my_gid: str, their_gid: str,
                    theirs: dict[str, Any]) -> dict[str, Any]:
    """Sibling filenames plus both teams' repos: a filed result must be
    navigable from itself alone."""
    played = [row["index"] for row in rt.sub_results]
    return {
        "declaration": game_ids.declaration_name(rt.game_id),
        "configs": [game_ids.config_name(rt.game_id, n) for n in played],
        "logs": [game_ids.log_name(rt.game_id, n) for n in played],
        "github": {my_gid: dict(rt.peer.repos),
                   their_gid: dict(theirs.get("repos") or {})},
    }


def email_report(rt: Any, result: dict[str, Any], transport: Any) -> dict[str, Any]:
    """Both teams send separately (#35); the Gatekeeper fronts the account.

    Rate config = versioned local defaults (rate_limits.json) overridden by
    the agreed constitution section - negotiated values always win.
    """
    from pathlib import Path

    from ..shared.config import load_rate_limits

    local = load_rate_limits(Path(f"config/{rt.role}"))
    gate = Gatekeeper.from_config({**local, **rt.shared.rate_limiter},
                                  daily_quota=local.get("daily_quota", 50))
    attachments = {f"result_{rt.game_id}.json": result}
    return send_report(
        transport=transport, gatekeeper=gate, to_addr=rt.peer.email_recipient,
        subject=f"[p2p-pursuit] result {rt.game_id}", attachments=attachments,
        mode=rt.peer.email_mode)


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
    from ..shared.config import hmac_secret

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
    from ..shared.config import hmac_secret

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
    start = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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
