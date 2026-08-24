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

import logging
import queue
import threading
from typing import Any

from ..domain.audit import NOT_REPORTED_REFERENCE
from ..report.result_agreement import APPROVAL_KIND
from . import interop_codec as codec
from .bridge_consensus import BridgeConsensus
from .bridge_handshake import BridgeHandshake
from .bridge_turns import BridgeTurns

log = logging.getLogger(__name__)


class ReferenceBridge(BridgeHandshake, BridgeConsensus, BridgeTurns):
    """One match's worth of translation between the two dialects."""

    def __init__(self, service: Any, link: Any, *, grid_size: int,
                 terms: dict[str, Any], identity: dict[str, Any],
                 runtime: Any = None) -> None:
        self.service, self.link = service, link
        #: The runtime, when one owns us - needed only to re-point the outbound
        #: link after a role swap. Optional so the bridge stays constructible on
        #: its own in tests.
        self.runtime = runtime
        self.grid_size, self.terms, self.identity = grid_size, terms, identity
        self.agreements: queue.Queue = queue.Queue()
        self._commit_hash: str | None = None
        self._owed_claim_response: dict | None = None
        self._owed_win_claim: dict | None = None
        self._last_turn: dict | None = None
        #: The sub-game `_last_turn` belongs to. A terminal claim is sent by
        #: repeating the last turn, so a stale one would replay a *previous*
        #: sub-game's commitment into this one's live stream.
        self._last_turn_sub_game: int | None = None
        #: Step-0 system-spec record per sub-game, sealed once (never at audit time).
        self._system_specs: dict[int, tuple[dict[str, Any], str]] = {}
        #: Per-sub-game result of auditing our own reveal before sending it.
        self.reveal_self_checks: dict[int, list[str]] = {}
        #: Their series digest, once an envelope passes the §10.3 gate.
        self.peer_consensus_sha: str | None = None
        #: Their §6 idempotent replay cache: one request -> one digest, forever.
        #: Keyed by the request's own content so a genuine second request (a
        #: different timestamp or different entries) is answered afresh, while a
        #: retransmission of the same one never triggers a second assembly.
        self._approval_answers: dict[tuple, str] = {}
        self._approval_lock = threading.Lock()
        #: The proposer's timestamp, adopted verbatim the first time we answer a
        #: request and echoed back on our own. Never regenerated: MaRs-777 fail
        #: closed on a re-stamped echo, and two peers each stamping their own
        #: clock could never agree on a document that carries one.
        self.approval_timestamp: str | None = None
        #: Our own digest for the agreed core, kept so the outbound direction can
        #: compare against what they answer without reassembling.
        self.approval_sha: str | None = None
        #: Their six entries exactly as contributed. Retained because BOTH
        #: directions hash the same core: our outbound request must be assembled
        #: from what they sent, never from anything we could derive ourselves.
        self.approval_their_entries: list[dict[str, Any]] | None = None
        #: Did the turn we just sent already carry the terminal win claim? If so
        #: the `event` that follows it in the same package has nothing left to
        #: deliver, and repeating the turn to say so is the bug this flag exists
        #: to prevent (see `_terminal_win_claim`).
        self._win_claim_sent = False
        #: Sub-game the scent-channel note has already been logged for.
        self._scent_note_for: int | None = None

    #: Turn to judge the scent channel on. NOT turn 1: a lagged trail is
    #: legitimately empty on the opening move - gal-roy1 send theirs lag-1, so
    #: their first turn carries `{}` by design. Sampling turn 1 reported "NO
    #: smell_grid" against a peer that does send one, which is worse than not
    #: checking: it is evidence pointing the wrong way. Their trail is populated
    #: from turn 2, so that is the first turn whose emptiness would mean anything.
    SCENT_NOTE_TURN = 2

    def _note_scent_channel(self, message: dict, sub_game: int) -> None:
        """Say once per sub-game whether their turns carry a pheromone field.

        `from_turn_message` substitutes an empty grid for a missing `smell_grid`,
        which is right - a peer that sends none must not crash us - but it makes
        the difference between "tracking them by scent" and "navigating on hints
        that are lies half the time" completely invisible. Our police captured
        nothing in nine sub-games against gal-roy1 and this line is what tells us
        whether it ever had a trail to follow.
        """
        if sub_game == self._scent_note_for:
            return
        try:
            step = int(message.get("step", 0))
        except (TypeError, ValueError):
            step = 0
        if step < self.SCENT_NOTE_TURN:
            return
        self._scent_note_for = sub_game
        cells = len(message.get("smell_grid") or {})
        log.info("sub-game %s: their turn %s %s", sub_game, step,
                 f"carries a smell_grid ({cells} cell{'' if cells == 1 else 's'})"
                 if cells else
                 "carries NO smell_grid - our belief runs on hints alone")

    def on_submit_audit(self, payload: dict) -> dict:
        """Their revealed log: audited on their terms, then filed where the rest
        of the pipeline looks for it.

        It cannot go through ``service.audit_exchange`` - that runs our own
        physics audit, which cannot read their record shape.

        The end-of-series consensus envelope arrives on this same tool and must
        be taken off it first: it carries no records, so auditing it would file
        an empty-log verdict over the *last sub-game's* real one and turn a
        finished series into a technical loss.
        """
        from ..report.consensus import CONSENSUS_CLAIM
        from .interop_audit import audit_reference_log

        engine = self.service.engine
        if payload.get("result_claim") == CONSENSUS_CLAIM:
            self._accept_consensus(payload, peer_role=engine.other)
            return {"ok": True}
        records = payload.get("records", [])
        n = self._declared_sub_game(payload, engine)
        verdict, violations = audit_reference_log(
            records, engine.opponent_hashes_for(n), grid_size=self.grid_size)
        cv = self.service.locked()
        with cv:
            self.service.audit_packages[n] = {
                "kind": "audit_package", "role": payload.get("sender", engine.other),
                "sub_game": n, "records": records}
            self.service.audit_verdicts[n] = {"verdict": verdict,
                                              "violations": violations}
            cv.notify_all()
        return {"ok": True}

    def on_receive_control(self, message: dict) -> dict | str:
        """Advisory channel, plus MaRs-777's one semantic kind.

        Every legacy form - `enable`, `status`, `restart`, `quit`, and anything
        unrecognised - keeps its exact `{"ok": true}` answer. Only
        `result_agreement` diverges, and it diverges completely: their §2 wants a
        **bare 64-character hex string** back, not an object and not `{"ok": true}`.
        Returning our usual envelope there reads to them as a malformed answer.
        """
        if isinstance(message, dict) and message.get("kind") == APPROVAL_KIND:
            return self._answer_result_agreement(message.get("payload") or {})
        return {"ok": True}

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
    def opponent_already_contacted(self) -> bool:
        """Have they reached us already? Then stop probing and handshake.

        Over a tunnel each failed liveness probe costs its full timeout, so
        sixty attempts take minutes - while a reference peer gives us only ~60 s
        to answer its `negotiate` before it exits with "Opponent never sent its
        agreement". An agreement sitting in our inbox is stronger evidence of
        liveness than any probe of ours could be: they demonstrably reached us.
        """
        return not self.agreements.empty()

    def health(self, timeout: float | None = None) -> dict:
        """They serve no health tool; reachability is the tool listing itself."""
        return {"ok": bool(self.link.list_tools(timeout=timeout))}

    def receive_control(self, message: dict, timeout: float | None = None) -> Any:
        """Outbound twin of `on_receive_control` - same seam, same cost.

        Returns a **bare 64-hex string** for `result_agreement`, so it must not
        be typed as a dict. Without this the call raised `AttributeError` into
        `exchange_result_agreement`'s own `except Exception`, which recorded a
        failed agreement rather than a missing method.
        """
        return self.link.receive_control(message, timeout=timeout)

    def audit(self, package: dict, timeout: float | None = None) -> dict:
        """Reveal our nonces in their envelope.

        Their ``submit_audit`` answers ``{"ok": True}``: a reference peer keeps
        its verdict of us to itself, so unlike a native match we cannot report
        what they made of our log - only that they received it. Ours answers the
        same way, so the blindness is symmetric and neither peer is withholding
        anything. That is why the sentinel returned here is
        `NOT_REPORTED_REFERENCE` and not "not received": see
        `report.results.agreement_reached`, which treats the two oppositely.

        The envelope **names its sub-game**. Without that the receiver has only
        one way to file it - against whichever index it has reached by the time
        the message lands - and the two peers do not cross a boundary at the
        same instant. Ours waits up to 20 s for their package before advancing;
        a peer that does not wait is already on n+1 when our sub-game n reveal
        arrives, files it there, and finds that none of its n+1 commitments
        bind and (under alternation) that every role label reads inverted.
        Both spellings are sent, and every record carries the index too, so it
        can be filed by content whichever key the reader looks for.
        """
        n = package.get("sub_game", self.service.engine.sub_game)
        end = self.service.engine.end
        spec, spec_hash = self._system_spec_record(n)
        records = codec.reference_records(
            [spec, *package["records"]], [spec_hash, *package.get("hashes", [])])
        self._self_check(records, package, n)
        self.note_tracker_coverage(n)
        self.link.submit_audit(
            {"sender": package["role"],
             "sub_game": n,
             "sub_game_number": n,
             "records": records,
             "result_claim": end.ending if end else "unknown"}, timeout=timeout)
        return {"verdict": NOT_REPORTED_REFERENCE, "violations": []}

    def _self_check(self, records: list[dict], package: dict, n: int) -> None:
        """Audit our own package as they will, and say so before it goes out.

        A reveal that does not bind is a technical loss whoever notices it, so
        the only useful moment to find out is here - not from the opponent, a
        sub-game later, with the series already spent.
        """
        from .interop_audit import verify_outgoing_reveal

        violations = verify_outgoing_reveal(
            records, package.get("hashes", []), sub_game=n, role=package["role"])
        if violations:
            log.error("sub-game %s: our own reveal FAILS its binding self-check "
                      "(%d violations): %s", n, len(violations), "; ".join(violations[:5]))
        else:
            log.info("sub-game %s: reveal self-check OK - %d records bind %d live "
                     "commitments", n, len(records), len(package.get("hashes", [])))
        self.reveal_self_checks[n] = violations

    def note_tracker_coverage(self, sub_game: int) -> None:
        """How many turns of this sub-game we actually knew where they were.

        Our evasion rests entirely on that number: measured under the kit's
        physics, our thief survives a homing pursuer 100% of the time with a fix
        and 20.8% without one. After losing three thief sub-games to uoh-ay26 at
        the same cell we could not tell which case we had been in, because a
        peer's sealed records carry its moves and not its scent - so the field we
        inverted at the time is not in the archive and the question was
        unanswerable after the fact. It is answerable at the time, so it is
        answered here.
        """
        tracker = getattr(self.service.engine, "opp_tracker", None)
        if tracker is None:
            return
        turns = max(self.service.engine.opp_steps, 1)
        log.info("sub-game %s: tracker had a fix on %s of %s of their turns%s",
                 sub_game, tracker.fixes, turns,
                 "" if tracker.fixes else " - WE PLAYED IT BLIND")

