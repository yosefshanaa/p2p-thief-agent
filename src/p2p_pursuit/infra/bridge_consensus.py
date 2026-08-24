"""The end-of-series agreement, from the reference peer's side - as a mixin.

Split out of :mod:`.interop_bridge` (§3.2, mixin strategy ch. 4.2). One
concern: answering their `result_agreement`, accepting or refusing a consensus
digest, and blocking until one arrives. A request that cannot be answered yet
is refused *retryably* - never held, never answered wrong.
"""

from __future__ import annotations

import logging
from typing import Any

from ..domain.protocol import record_sub_game
from ..report.result_agreement import NotReadyError

log = logging.getLogger(__name__)

class BridgeConsensus:
    def _answer_result_agreement(self, payload: dict) -> str | dict:
        """Merge their contribution with ours and return `result_sha256`.

        Bounded readiness (their §6): a correct request can arrive while we are
        still assembling our own six entries, because both peers finish sub-game
        six at different moments. That is not an error - we wait, then answer the
        *same* request. Idempotent by their §6 too: a repeat of a request we have
        already answered returns the identical digest rather than reassembling.
        """
        if self.runtime is None:
            return {"ok": False, "error": "no runtime owns this bridge"}
        their = payload.get("contribution") or {}
        their_gid = their.get("group_id") or ""
        entries = their.get("entries") or []
        key = (payload.get("timestamp") or "", their_gid,
               tuple((e.get("sub_game"), e.get("github_commit"), e.get("tokens"))
                     for e in entries))
        with self._approval_lock:
            if key in self._approval_answers:
                return self._approval_answers[key]
        from ..peer.report_agreement import runtime_result_agreement

        try:
            sha = runtime_result_agreement(self.runtime, payload,
                                           their_gid=their_gid, entries=entries)
        except NotReadyError as exc:
            # Explicitly retryable, and nothing mutated - their §6.
            return {"ok": False, "error": "E-NOT-READY", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - a refusal is a fact, not a crash
            log.warning("result_agreement refused: %s", exc)
            return {"ok": False, "error": "E-REPORT-DISAGREE", "detail": str(exc)}
        with self._approval_lock:
            self._approval_answers[key] = sha
            if self.approval_timestamp is None:
                self.approval_timestamp = payload.get("timestamp") or ""
            self.approval_sha = sha
            self.approval_their_entries = list(entries)
        return sha

    def _declared_sub_game(self, payload: dict, engine: Any) -> int:
        """Which sub-game an inbound reveal is *for* - asked, not assumed.

        Filing by arrival is the bug we are fixing on our own side of the wire,
        so we stop doing it here too. The envelope is authoritative if it says;
        otherwise the records do, because ours and theirs both carry the index
        in every payload. Only then does the index we happen to be on decide.
        """
        for key in ("sub_game", "sub_game_number"):
            value = payload.get(key)
            if isinstance(value, int) and value > 0:
                return value
        declared = {n for n in (record_sub_game(r) for r in payload.get("records", []))
                    if n is not None}
        if len(declared) == 1:
            return declared.pop()
        if len(declared) > 1:
            log.warning("their reveal spans sub-games %s - filing it against ours (%s)",
                        sorted(declared), engine.sub_game)
        return engine.sub_game

    # -- series consensus (their §10.3) --------------------------------------
    def _accept_consensus(self, payload: dict, *, peer_role: str) -> None:
        """Store their digest if the envelope passes the gate they specify.

        Strict first, on all three of claim / sender-role / empty records. If
        only the role disagrees we take the digest anyway and say so: the role
        is bookkeeping about *which side sent it*, already implied by the
        connection, and a series that played cleanly should not fail to confirm
        because two peers label the last sub-game's wire role differently.
        """
        from ..report.consensus import peer_consensus_sha

        sha = peer_consensus_sha(payload, peer_role=peer_role)
        if sha is None:
            sha = peer_consensus_sha(payload)
            if sha is not None:
                log.warning("consensus envelope sender=%r, expected %r - digest accepted",
                            payload.get("sender"), peer_role)
        if sha is None:
            log.warning("consensus envelope refused: %s",
                        {k: payload.get(k) for k in ("sender", "records", "consensus_sha")})
            return
        cv = self.service.locked()
        with cv:
            self.peer_consensus_sha = sha
            cv.notify_all()

    def submit_consensus(self, envelope: dict, timeout: float | None = None) -> dict:
        """Push our digest on the raw link - the bridge's own ``audit`` wraps
        records, and this envelope is defined by carrying none."""
        return self.link.submit_audit(envelope, timeout=timeout)

    def wait_for_consensus(self, timeout: float) -> str | None:
        cv = self.service.locked()
        with cv:
            cv.wait_for(lambda: self.peer_consensus_sha is not None, timeout)
            return self.peer_consensus_sha
