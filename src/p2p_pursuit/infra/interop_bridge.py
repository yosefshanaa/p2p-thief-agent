"""Playing a reference-derived peer without either side rewriting its engine.

Their transport is push-and-inbox: every tool returns ``{"ok": True}`` and the
reply arrives later as a separate call into *our* server. Ours is
request/response. The bridge owns that asymmetry so `PeerRuntime` keeps the
link surface it already uses:

* outbound - fold our commit+reveal into their one `receive_turn`, then block
  on the matching inbox for the answer their peer pushes back;
* inbound - split their turn into our commit/reveal handlers, and carry the
  claim answer and win claim we owe them onto our next outbound message,
  because their protocol has nowhere else to put them.
"""

from __future__ import annotations

import queue
from typing import Any

from ..domain.protocol import KIND_CAPTURE_ANSWER
from . import interop_codec as codec
from .transport import LinkError


class ReferenceBridge:
    """One match's worth of translation between the two dialects."""

    def __init__(self, service: Any, link: Any, *, grid_size: int,
                 terms: dict[str, Any], identity: dict[str, Any]) -> None:
        self.service, self.link = service, link
        self.grid_size, self.terms, self.identity = grid_size, terms, identity
        self.agreements: queue.Queue = queue.Queue()
        self._commit_hash: str | None = None
        self._owed_claim_response: dict | None = None
        self._owed_win_claim: dict | None = None

    # -- inbound: their pushes into our server -------------------------------
    def on_negotiate(self, message: dict) -> dict:
        self.agreements.put(message)
        return {"ok": True}

    def on_receive_turn(self, message: dict) -> dict:
        """Their whole turn, replayed through our two inbound handlers.

        Their agreement carries no role, so a both-sides-play-police mix-up is
        only detectable here, on the first turn that names its sender.
        """
        engine = self.service.engine
        if message.get("sender") == engine.role:
            with self.service.locked():
                engine.declare_technical(
                    engine.other, f"both peers claim role {engine.role!r}")
            return {"ok": False, "error": "role collision"}
        parts = codec.from_turn_message(message, sub_game=engine.sub_game,
                                        grid_size=self.grid_size)
        self.service.receive_commit(parts["commit"])
        response = self.service.receive_reveal(parts["reveal"])
        for envelope in response.get("events", []):
            self._owe(envelope)
        if parts["claim_response"] or parts["win_claim"]:
            self._apply_side_channels(parts)
        return {"ok": True}

    def on_submit_audit(self, payload: dict) -> dict:
        """Their revealed log: audited on their terms, then filed where the rest
        of the pipeline looks for it.

        It cannot go through ``service.audit_exchange`` - that runs our own
        physics audit, which cannot read their record shape.
        """
        from .interop_audit import audit_reference_log

        engine = self.service.engine
        records = payload.get("records", [])
        verdict, violations = audit_reference_log(
            records, engine.opp_hashes, grid_size=self.grid_size)
        cv = self.service.locked()
        with cv:
            n = engine.sub_game
            self.service.audit_packages[n] = {
                "kind": "audit_package", "role": payload.get("sender", engine.other),
                "sub_game": n, "records": records}
            self.service.audit_verdicts[n] = {"verdict": verdict,
                                              "violations": violations}
            cv.notify_all()
        return {"ok": True}

    def on_receive_control(self, message: dict) -> dict:
        """Advisory channel we do not act on; accepted so their peer is not stalled."""
        return {"ok": True}

    def _owe(self, envelope: dict) -> None:
        """Queue an answer their protocol can only carry on our next turn."""
        public = envelope.get("public", {})
        if public.get("kind") == KIND_CAPTURE_ANSWER:
            self._owed_claim_response = {"claim": list(public["claim_cell"]),
                                         "caught": bool(public["answer"])}

    def _apply_side_channels(self, parts: dict) -> None:
        """Their unsealed claim answer / win claim, fed to our engine as events.

        Neither field is covered by their commit, so what arrives here is taken
        on trust - recorded as such, never mixed into the sealed audit trail.
        """
        from ..peer import unsealed_events

        engine = self.service.engine
        with self.service.locked():
            answer = parts["claim_response"]
            if answer and answer.get("caught"):
                unsealed_events.note_capture_confirmed(engine, list(answer["claim"]))
            win = parts["win_claim"]
            if win:
                unsealed_events.note_survival_claimed(
                    engine, str(win.get("type", "survival")))

    # -- outbound: our link surface, spoken in their dialect ------------------
    def health(self, timeout: float | None = None) -> dict:
        """They serve no health tool; reachability is the tool listing itself."""
        return {"ok": bool(self.link.list_tools(timeout=timeout))}

    def handshake(self, payload: dict, timeout: float | None = None) -> dict:
        """Push our signed agreement, then wait for theirs on the inbox."""
        self.link.negotiate(self._signed(), timeout=timeout)
        try:
            theirs = self.agreements.get(timeout=timeout or 60)
        except queue.Empty as exc:
            raise LinkError("opponent never sent its agreement") from exc
        return codec.handshake_from_agreement(theirs, mine=payload, terms=self.terms)

    def _signed(self) -> dict:
        from ..domain.crypto import new_nonce, reference_commit

        nonce = new_nonce()
        return {"terms": self.terms, "nonce": nonce,
                "signature": reference_commit(self.terms, nonce),
                "identity": self.identity}

    def commit(self, msg: dict, timeout: float | None = None) -> dict:
        """Hold the hash: their protocol carries it on the turn message itself."""
        self._commit_hash = msg["hash"]
        return {"ack": True, "locked": True}

    def reveal(self, pub: dict, timeout: float | None = None) -> dict:
        message = codec.to_turn_message(
            pub, commit_hash=self._commit_hash,
            claim_response=self._owed_claim_response, win_claim=self._owed_win_claim)
        self._commit_hash = None
        self._owed_claim_response = self._owed_win_claim = None
        self.link.receive_turn(message, timeout=timeout)
        return {"ok": True, "events": []}

    def event(self, envelope: dict, timeout: float | None = None) -> dict:
        """Our sealed events have no standalone message; they ride the next turn."""
        public = envelope.get("public", {})
        if public.get("kind") == KIND_CAPTURE_ANSWER:
            self._owed_claim_response = {"claim": list(public["claim_cell"]),
                                         "caught": bool(public["answer"])}
        else:
            self._owed_win_claim = {"type": public.get("kind", "survival")}
        return {"ok": True}

    def audit(self, package: dict, timeout: float | None = None) -> dict:
        """Reveal our nonces in their envelope.

        Their ``submit_audit`` answers ``{"ok": True}``: a reference peer keeps
        its verdict of us to itself, so unlike a native match we cannot report
        what they made of our log - only that they received it.
        """
        end = self.service.engine.end
        self.link.submit_audit(
            {"sender": package["role"],
             "records": codec.reference_records(package["records"]),
             "result_claim": end.ending if end else "unknown"}, timeout=timeout)
        return {"verdict": "not reported (reference dialect)", "violations": []}
