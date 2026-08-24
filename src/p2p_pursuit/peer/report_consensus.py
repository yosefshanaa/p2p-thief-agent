"""The end-of-series consensus exchange, and who the opponent is.

Split out of :mod:`.runtime_reports` (§3.2 - split, never compress). One
concern: agreeing a single digest over all six rows with the peer, including
the group-id hint Step-0 needs before any handshake has happened.
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..domain.audit import VERIFIED_OK
from ..report import consensus

#: Their slug, when we would otherwise have to wait for the wire to tell us.
#: Step-0 goes out *before* any handshake, so at that moment the wire has told
#: us nothing - and both shared ids are pure functions of the agreed terms and
#: the two slugs, so one configured value is the whole difference between a
#: Step-0 that names this game and one their runtime refuses as stale.
OPPONENT_GROUP_ID_VAR = "P2P_OPPONENT_GROUP_ID"


def their_group_id_hint() -> str:
    return (os.environ.get(OPPONENT_GROUP_ID_VAR) or "").strip()


def _their_group_id(rt: Any) -> str:
    return ((rt.service.their_handshake or {}).get("group_id")
            or their_group_id_hint() or "opponent")


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
