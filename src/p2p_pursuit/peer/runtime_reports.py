"""Runtime reporting side: declaration, per-sub-game audit + artifacts, result, email."""

from __future__ import annotations

import contextlib
import time
from typing import Any

from ..domain import declarations, game_ids, negotiation
from ..domain.audit import VERIFIED_OK
from ..domain.crypto import digest
from ..domain.scoring import TECHNICAL_LOSS
from ..infra.email_sender import send_report
from ..report import artifacts, consensus, mutual_signature, results
from ..shared import sysinfo
from ..shared.gatekeeper import Gatekeeper
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
