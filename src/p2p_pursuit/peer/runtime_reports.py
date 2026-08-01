"""Runtime reporting side: declaration, per-sub-game audit + artifacts, result, email."""

from __future__ import annotations

import contextlib
from typing import Any

from ..domain import declarations, negotiation
from ..domain.scoring import TECHNICAL_LOSS
from ..infra.email_sender import send_report
from ..report import artifacts, results
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
        scent_model_sha256=negotiation.scent_model_sha256(),
        token_cap=rt.shared.network.get("token_budget_per_series", 200000),
        me=me, opponent=opp)
    artifacts.write_declaration(rt.out_dir, rt.game_id, decl)


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
    their_view = {"verdict": "not received", "violations": []}
    with contextlib.suppress(DeadlineExpiredError):
        their_view = rt.deadline.call(rt.link.audit, audit_bridge.audit_package(engine))
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
    audit_blob = {"mine_of_them": my_verdict, "theirs_of_us": their_view}
    log = log_manager.build_log(engine, opp_records, game_uid=rt.game_uid,
                                game_id=rt.game_id, audit=audit_blob)
    log_manager.write_log(log, rt.out_dir)
    artifacts.write_config_copy(rt.out_dir, rt.game_id, n, rt.shared.raw, rt.game_uid)
    row = results.sub_game_row(
        index=n, ending=ending, winner=winner, cause=cause,
        police_score=p_score, thief_score=t_score,
        moves_played=engine.my_steps if rt.role == "thief" else engine.opp_steps,
        github_commit=sysinfo.git_commit(), audit_verdict=my_verdict["verdict"],
        opponent_audit=their_view["verdict"])
    log_fn(f"[{rt.role}] sub-game {n}: {ending} winner={winner} ({cause}) "
           f"audit={my_verdict['verdict']}")
    return row


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
    artifacts.write_result(rt.out_dir, rt.game_id, result)
    return result


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
