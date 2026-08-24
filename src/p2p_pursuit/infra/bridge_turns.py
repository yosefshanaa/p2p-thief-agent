"""Turns over the reference dialect: push, inbox, and the answers we owe.

Split out of :mod:`.interop_bridge` (§3.2, mixin strategy ch. 4.2). One
concern: their push-and-inbox framing. Every tool returns {"ok": true} and the
reply arrives as a separate push, so what is owed has to be tracked explicitly
- a claim answer reaches the bridge through `_owe`, never through `event`, and
a terminal one has to be flushed before the window closes.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from ..domain.protocol import KIND_CAPTURE_ANSWER, KIND_CAPTURED_EVENT
from ..domain.rules import THIEF
from ..domain.scoring import SURVIVAL
from . import interop_codec as codec

log = logging.getLogger(__name__)

class BridgeTurns:
    def on_receive_turn(self, message: dict) -> dict:
        """Their whole turn, replayed through our two inbound handlers.

        Their agreement carries no role, so a both-sides-play-police mix-up is
        only detectable here, on the first turn that names its sender.
        """
        engine = self.service.engine
        if message.get("sender") == engine.role:
            with self.service.locked():
                if not self._resolve_role_collision(engine):
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

    def _resolve_role_collision(self, engine: Any) -> bool:
        """Take the other side rather than forfeit the sub-game. True if we did.

        The re-handshake path has done this since the orcai-mj post-mortem, but
        a peer configured with `handshake_per_sub_game` off never takes that
        path - its first sign of a drifted index is a turn that names our own
        role, and this handler forfeited on the spot. Ten sub-games in the
        archive end "both peers claim role X", and not one of them is the first
        failure of its match: they are all the *second*, where one abandoned
        sub-game desynchronised the two indices and every later sub-game of the
        same parity collided. That is how a single 502 has repeatedly taken a
        whole six-game series.

        Only before we have committed anything to this sub-game. Swapping role
        mid-sub-game would re-enter it and discard steps we have already sealed
        and sent, turning a recoverable collision into an audit failure, which
        is the same technical loss by a longer route.
        """
        # Read defensively: a series that does not alternate has no schedule to
        # be drifted and must still forfeit, which is also what an engine that
        # cannot answer these should do.
        if not getattr(getattr(engine, "peer", None), "alternate_roles", False):
            return False
        adopt = getattr(engine, "adopt_complementary_role", None)
        if not callable(adopt) or getattr(engine, "my_steps", 0):
            return False
        took = adopt(engine.sub_game)
        self.service.my_handshake["role"] = took
        log.info("sub-game %s: they claim our role; taking %r instead of "
                 "forfeiting - their index has drifted from ours",
                 engine.sub_game, took)
        if self.runtime is not None:
            from ..peer.series_protocol import retarget_link

            retarget_link(self.runtime, took, lambda m: log.info("%s", m))
        return True

    def _owe(self, envelope: dict) -> None:
        """Queue an answer their protocol can only carry on our next turn.

        THIS is the live path for a claim answer, not :meth:`event` - the engine
        *returns* the sealed answer from `_answer_claim` and `on_receive_turn`
        hands it here, so nothing routes through the event surface. F002 was lost
        to exactly that distinction: the same fix was applied to :meth:`event`,
        proved by a unit test that called :meth:`event` directly, and the wire
        never touched it. All six thief windows across F001 and F002 came back
        `audit=no package received`.

        `caught: true` is terminal, so there is no next turn to carry it and it
        must be flushed now. `timeout` is None because `on_receive_turn` has none
        to give; `_flush_terminal` treats that as the link default and already
        suppresses send failures, so a courtesy message can never turn a won
        sub-game into an error.
        """
        public = envelope.get("public", {})
        if public.get("kind") == KIND_CAPTURE_ANSWER:
            caught = bool(public["answer"])
            self._owed_claim_response = {"claim": list(public["claim_cell"]),
                                         "caught": caught}
            if caught:
                self._flush_terminal(None, hint="You got me.")

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
        self.link.receive_turn(message, timeout=self._turn_timeout(timeout))
        return {"ok": True, "events": []}

    def _turn_timeout(self, timeout: float | None) -> float:
        """Our configured turn budget, never fastmcp's 30s default.

        `runtime.py:385` pushes a turn as `deadline.call(link.event, ...)` with
        no timeout, so `timeout` arrives None and `Client(url, timeout=None)`
        falls back to **30 seconds** - a quarter of the 180 we configure. We
        then hang up on a peer that is still thinking and abandon the sub-game,
        which with P2P_WINDOW_REOFFERS=0 is unrecoverable. Diagnosed twice as
        the opponent's bounded wait; it was ours both times.
        """
        if timeout is not None:
            return timeout
        peer = getattr(self.runtime, "peer", None)
        return float(getattr(peer, "turn_timeout_seconds", 180) or 180)

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
            # An answer of `false` is not terminal, so it rides the next turn.
            # `true` IS terminal, and that is the whole of this branch's history:
            # the sub-game ends on it, so there is no next turn to carry it, and
            # left to ride it dies in the buffer while we go straight to
            # submit_audit. Exactly the win-claim shape documented above, missed
            # here because answering a claim reads like an ordinary reply.
            #
            # Found live against vibecode 2026-08-22 (F001), who diagnosed it
            # from their side before we did: all three of our thief windows were
            # captured, detected and sealed correctly - the `capture_answer`
            # record carries `answer: true` on the right cell - and all three
            # came back `audit=no package received` with zero opponent records,
            # because their cop was still waiting for the answer turn their
            # protocol calls the settlement. Their rule, which we accepted in
            # writing: "caught: true is terminal".
            caught = bool(public["answer"])
            self._owed_claim_response = {"claim": list(public["claim_cell"]),
                                         "caught": caught}
            if caught:
                self._flush_terminal(timeout, hint="You got me.")
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
            self.link.receive_turn(final, timeout=self._turn_timeout(timeout))
