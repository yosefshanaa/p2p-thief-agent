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

import contextlib
import logging
import queue
from datetime import UTC, datetime
from typing import Any

from ..domain.protocol import KIND_CAPTURE_ANSWER, KIND_CAPTURED_EVENT, record_sub_game
from ..domain.rules import THIEF
from ..domain.scoring import SURVIVAL
from . import interop_codec as codec
from .transport import LinkError

log = logging.getLogger(__name__)


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
        #: Did the turn we just sent already carry the terminal win claim? If so
        #: the `event` that follows it in the same package has nothing left to
        #: deliver, and repeating the turn to say so is the bug this flag exists
        #: to prevent (see `_terminal_win_claim`).
        self._win_claim_sent = False
        #: Sub-game the scent-channel note has already been logged for.
        self._scent_note_for: int | None = None

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
        self._note_scent_channel(message, engine.sub_game)
        parts = codec.from_turn_message(message, sub_game=engine.sub_game,
                                        grid_size=self.grid_size)
        self.service.receive_commit(parts["commit"])
        response = self.service.receive_reveal(parts["reveal"])
        for envelope in response.get("events", []):
            self._owe(envelope)
        if parts["claim_response"] or parts["win_claim"]:
            self._apply_side_channels(parts)
        return {"ok": True}

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

    def on_receive_control(self, message: dict) -> dict:
        """Advisory channel we do not act on; accepted so their peer is not stalled."""
        return {"ok": True}

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
        # `sub_game_number` rides outside `terms`, so it cannot disturb the
        # signature - but without it a peer that has advanced past us looks
        # identical to one in step, and the two series drift in silence.
        return {"terms": self.terms, "nonce": nonce,
                "signature": reference_commit(self.terms, nonce),
                "sub_game_number": self.service.engine.sub_game,
                "identity": self.identity}

    def commit(self, msg: dict, timeout: float | None = None) -> dict:
        """Hold the hash: their protocol carries it on the turn message itself."""
        self._commit_hash = msg["hash"]
        return {"ack": True, "locked": True}

    def reveal(self, pub: dict, timeout: float | None = None) -> dict:
        win = self._owed_win_claim or self._terminal_win_claim()
        message = codec.to_turn_message(
            pub, commit_hash=self._commit_hash,
            claim_response=self._owed_claim_response, win_claim=win)
        self._commit_hash = None
        self._owed_claim_response = self._owed_win_claim = None
        self._win_claim_sent = win is not None
        self._last_turn = message
        self._last_turn_sub_game = self.service.engine.sub_game
        self.link.receive_turn(message, timeout=timeout)
        return {"ok": True, "events": []}

    def _terminal_win_claim(self) -> dict | None:
        """The survival declaration belongs on the step that earns it.

        `next_package` seals the survival claim while it builds the same package
        as the reveal (turn_engine.py), so by the time we are called the engine
        has already finished the sub-game - the claim is knowable *before* the
        first send, not only when the `event` arrives afterwards.

        That ordering is the whole point. Their inbox keys on (step, commit) and
        absorbs a later message with the same pair as an HTTP redelivery, so a
        claim stamped onto a resend of an already-delivered step is never
        adjudicated. Measured live 2026-08-17 vs s82kma9e: our correctly-shaped
        `{"type": "survival"}` rode a second copy of step 35 sent 0.2 s after the
        first, their receiver absorbed it silently, and their police then waited
        its full 180 s turn deadline over a survival we had already declared -
        which desynchronised the series and voided three sub-games.
        """
        engine = self.service.engine
        if engine.role != THIEF or engine.end is None:
            return None
        if engine.end.ending != SURVIVAL:
            return None
        if engine.my_steps < engine.shared.survival_threshold:
            return None
        return {"type": "survival"}

    def event(self, envelope: dict, timeout: float | None = None) -> dict:
        """Our sealed events have no standalone message; they ride the next turn.

        A **win claim** is the exception, because it is terminal: the sub-game
        is over, so there is no next turn to carry it. Left to ride, their peer
        waits out its turn timeout - and `timeout` sits in their
        `NO_AUDIT_RESULTS`, so they skip the audit exchange altogether. Measured
        live 2026-08-01: every even sub-game (us as thief, surviving 35 steps)
        came back `audit=no package received` with zero opponent records.
        """
        public = envelope.get("public", {})
        kind = public.get("kind")
        engine = self.service.engine
        if kind == KIND_CAPTURE_ANSWER:
            # Answering a claim is not terminal, so it rides the next turn.
            self._owed_claim_response = {"claim": list(public["claim_cell"]),
                                         "caught": bool(public["answer"])}
        elif kind == KIND_CAPTURED_EVENT and engine.role == THIEF:
            # Book 46/47: a barrier on our own cell, or no legal move left. Only
            # the thief can observe it, and in this dialect the thief *announces*
            # it as a claim answer about its own cell - `win_claim` is reserved
            # for survival, so sending one here reads as the wrong ending.
            self._owed_claim_response = {"claim": list(engine.own_pos), "caught": True}
            self._flush_terminal(timeout, hint="You got me.")
        elif self._win_claim_sent:
            # The reveal in this same package already carried it. Their sender
            # builds the claim into the step that earns it and sends that once;
            # repeating the turn to restate it is exactly what their inbox
            # discards as a redelivery.
            self._win_claim_sent = False
        else:
            # Survival, or a police-side enclosure claim - which this dialect
            # cannot express, so it stays on the win-claim path it has always
            # used. Their vocabulary is "survival", not our internal kind name.
            self._owed_win_claim = {
                "type": "capture" if kind == KIND_CAPTURED_EVENT else "survival"}
            self._flush_terminal(timeout)
        return {"ok": True}

    def _flush_terminal(self, timeout: float | None, *, hint: str | None = None) -> None:
        """Send the terminal claim on a copy of our last turn.

        Their protocol has no standalone end-of-game message - a win claim is a
        field on a TurnMessage - so we repeat the last one we sent with the claim
        attached. Re-sending a commit they already hold is safe: their audit
        re-verifies hash binding inside our revealed records, not against the
        turns they received, and their handler ends the game the moment it reads
        the claim, so the duplicated belief update never affects a decision.
        """
        if self._last_turn is None or (
                self._owed_win_claim is None and self._owed_claim_response is None):
            return
        if self._last_turn_sub_game != self.service.engine.sub_game:
            # The last turn we sent belongs to a finished sub-game. Repeating it
            # now would put a previous sub-game's commitment into this one's live
            # stream - a commitment this sub-game's reveal correctly does not
            # contain, which reads to the opponent as a withheld record.
            log.warning("terminal claim for sub-game %s has no turn of its own to "
                        "ride (last turn was sub-game %s) - dropped rather than "
                        "replaying a settled sub-game's commitment",
                        self.service.engine.sub_game, self._last_turn_sub_game)
            self._last_turn = None
            self._last_turn_sub_game = None
            self._owed_win_claim = self._owed_claim_response = None
            return
        final = dict(self._last_turn)
        if self._owed_win_claim is not None:
            final["win_claim"] = self._owed_win_claim
        if self._owed_claim_response is not None:
            final["claim_response"] = self._owed_claim_response
        if hint is not None:
            final["hint"] = hint
        final["timestamp"] = datetime.now(UTC).isoformat()
        self._owed_win_claim = self._owed_claim_response = None
        # Best effort: the opponent may already have stopped listening, and a
        # failed courtesy message must never turn a won sub-game into an error.
        with contextlib.suppress(Exception):
            self.link.receive_turn(final, timeout=timeout)

    def audit(self, package: dict, timeout: float | None = None) -> dict:
        """Reveal our nonces in their envelope.

        Their ``submit_audit`` answers ``{"ok": True}``: a reference peer keeps
        its verdict of us to itself, so unlike a native match we cannot report
        what they made of our log - only that they received it.

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
        return {"verdict": "not reported (reference dialect)", "violations": []}

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

    def _system_spec_record(self, sub_game: int) -> tuple[dict[str, Any], str]:
        """The step-0 record naming the code that played this sub-game.

        A reference peer reads `github_commit` out of our *revealed records* and
        files it per sub-game; there is nowhere else in this dialect for it to
        come from, so omitting the record does not leave their report blank -
        it leaves it saying `unknown` about us. Sealed like any other record so
        the claim is bound rather than asserted.

        Sealed **once per sub-game and cached**: this used to mint a fresh nonce
        on every call, so a retried `submit_audit` revealed the same claim under
        two different commitments. Nothing about an audit may be generated at
        audit time.
        """
        cached = self._system_specs.get(sub_game)
        if cached is not None:
            return cached
        from ..domain.crypto import commit_digest, new_nonce
        from ..shared import sysinfo

        engine = self.service.engine
        record = {"kind": "system_spec", "type": "system_spec", "step": 0,
                  "role": engine.audit_snapshot(sub_game)["role"],
                  "sub_game": sub_game, "sub_game_number": sub_game,
                  "github_commit": sysinfo.git_commit(), "nonce": new_nonce()}
        sealed = (record, commit_digest(record, engine.commit_dialect))
        self._system_specs[sub_game] = sealed
        return sealed
