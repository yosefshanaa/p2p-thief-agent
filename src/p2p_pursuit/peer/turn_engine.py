"""TurnEngine: one peer's protocol handlers for a single sub-game.

Transport-agnostic and single-threaded: ``build_own_step`` produces the
outbound commit/reveal package; ``on_*`` handlers process inbound messages.
State and bookkeeping live in engine_state.EngineState.
"""

from __future__ import annotations

from typing import Any

from ..domain import protocol
from ..domain.crypto import seal
from ..domain.hints import parse_hint
from ..domain.rules import POLICE, THIEF, apply_decision, safe_decision
from ..domain.scoring import CAPTURE, SURVIVAL
from .engine_state import EngineState, SubGameEnd
from .state_machine import (
    AWAITING_REVEAL,
    COMMITTING,
    COMPUTING_MOVE,
    VERIFYING,
    WAITING_FOR_OPPONENT,
)
from .turn_claims import TurnClaims

__all__ = ["SubGameEnd", "TurnEngine"]


class TurnEngine(TurnClaims, EngineState):
    def _advance(self, *states: str) -> bool:
        """Move the phase machine unless this sub-game is already over.

        The engine is driven from two places at once - our own series loop and
        the opponent's inbound pushes - so a turn can still be in flight when a
        timeout or an inbound event ends the sub-game. Reaching a terminal state
        first is a *race*, not a logic bug, and the machine's strictness exists
        to catch illegal play (rules #4-5), not to punish an in-flight turn for
        arriving after the ending.

        Measured live vs orcai-mj 2026-08-13: `link.reveal` is a network
        round-trip, an inbound push declared a technical loss during it, and the
        `sent_reveal` that followed raised `TECHNICAL_LOSS -> VERIFYING` out of
        the series thread. That killed the whole peer - our endpoint went 502
        and the opponent, who was retrying correctly, could never reconnect.
        """
        if self.end is not None:
            return False
        for state in states:
            self.machine.transition(state)
        return True

    # -- my move ------------------------------------------------------------
    def build_own_step(self) -> dict[str, Any]:
        """Produce this peer's next protocol package (step, or a forced event)."""
        if not self._advance(COMPUTING_MOVE):
            return {}
        if self.role == THIEF and self.board.is_enclosed(self.own_pos):
            return {"event": self._captured_event("enclosed")}
        # Book 3.4 says an enclosed thief is captured, and it wins games - but
        # only against an opponent that implements it. An unmodified reference
        # peer keeps playing, never sends its audit package, and every later
        # sub-game collides on roles. Negotiate it, then switch it on.
        if self.role == POLICE and self.peer.claim_enclosure:
            trapped = self._enclosed_opponent()
            if trapped is not None:
                return {"event": self._enclosure_claim(trapped)}
        view = self._view()
        decision = safe_decision(self.board, self.role, self.own_pos, self.barriers_used,
                                 self.shared.max_barriers, self.brain.decide(view))
        # A brain that spends tokens to *decide* has to be covered by the budget
        # seal too, not only the verbal channel below. Brains that spend none do
        # not define the hook and contribute nothing.
        take_tokens = getattr(self.brain, "take_tokens", None)
        if take_tokens is not None:
            self.tokens_used += take_tokens()
        region, intent = self.brain.hint_plan(view, decision)
        hint, tokens = self._make_hint(region)
        self.tokens_used += tokens
        pos_before = self.own_pos
        self.own_pos = apply_decision(self.board, self.own_pos, decision)
        if decision.barrier is not None:
            self.barriers_used += 1
        self.my_steps += 1
        # One call owns both the update and the serve-order, because the two
        # negotiated models disagree about which comes first.
        served = self.own_field.serve_for_step(self.own_pos)
        self.history.append(
            {"role": self.role, "step": self.my_steps, "barrier": decision.barrier})
        self.hint_feed.append({"dir": "sent", "step": self.my_steps, "hint": hint,
                               "intent": intent})
        record = protocol.step_record(
            role=self.role, sub_game=self.sub_game, step=self.my_steps,
            pos_before=pos_before, pos_after=self.own_pos, move=decision.move,
            barrier=decision.barrier, intent=intent, hint=hint, scent=served)
        sealed, h = seal(record, self.commit_dialect)
        public = self._record(sealed, h)
        self.machine.transition(COMMITTING)
        commit = {"kind": "commit", "role": self.role, "sub_game": self.sub_game,
                  "step": self.my_steps, "hash": h}
        package: dict[str, Any] = {"commit": commit, "reveal": public}
        if self.role == POLICE and (self.peer.always_claim
                                    or self.brain.should_claim(view, self.own_pos)):
            # Claim rides inside the reveal: the answer returns atomically, no race.
            package["reveal"]["claim"] = {"cell": list(self.own_pos), "at_step": self.my_steps}
            # Remembered so a later `caught: true` can be read for what it is: the
            # same cell is an answer, any other cell is a rule-46/47 concession
            # and wants corroborating against our own barriers (unsealed_events).
            self.last_claim_cell = tuple(self.own_pos)
        if self.role == THIEF and self.my_steps >= self.shared.survival_threshold:
            package["event"] = self._survival_claim()
        return package

    def sent_commit(self) -> None:
        self._advance(AWAITING_REVEAL)

    def sent_reveal(self) -> None:
        if not self._advance(VERIFYING, WAITING_FOR_OPPONENT):
            return
        self.next_mover = self.other

    # -- opponent's move ----------------------------------------------------
    def on_commit(self, msg: dict) -> dict:
        self._pending_commit = msg["hash"]
        return {"ack": True, "locked": True}

    def on_reveal(self, pub: dict) -> dict:
        """Process the opponent's public reveal; may return forced events (capture)."""
        self._note_opp(self._pending_commit or pub.get("hash", ""), pub)
        self._pending_commit = None
        self.opp_turn_times.append(pub.get("timestamp"))
        self.opp_steps += 1
        barrier = tuple(pub["barrier"]) if pub.get("barrier") else None
        self.history.append({"role": self.other, "step": self.opp_steps, "barrier": barrier})
        self.hint_feed.append({"dir": "received", "step": self.opp_steps,
                               "hint": pub.get("hint", "")})
        events: list[dict] = []
        if barrier:
            self.board.add_barrier(barrier)
            if self.role == THIEF and barrier == self.own_pos:
                events.append(self._barrier_capture(barrier))
        # Read their cell off the field they just published, before anything
        # downstream needs it. Their own barrier is already on our board, so the
        # continuity scan cannot propose a cell they could not be standing in.
        if pub.get("scent"):
            self.opp_tracker.observe(pub["scent"], self.board)
        if self.end is None:
            self._update_belief(pub)
        if self.end is None and pub.get("claim") and self.role == THIEF:
            events.append(self._answer_claim(pub["claim"]))
        self.next_mover = self.role
        return {"ok": True, "events": events}

    def _update_belief(self, pub: dict) -> None:
        self.belief.scent_update(pub["scent"], self.board)
        self.belief.diffuse(self.board)
        region = parse_hint(pub.get("hint", ""), self.shared.grid_size, self.shared.map_area)
        if region:
            scent = pub["scent"]
            peak = max(max(row) for row in scent)
            mass = sum(scent[r][c] for r, c in region) / max(sum(map(sum, scent)), 1e-9)
            self.trust.judge(mass, peak)
            self.belief.hint_update(region, self.trust.value, self.board)

    def on_event(self, envelope: dict) -> dict:
        pub = envelope["public"]
        self._note_opp(envelope["hash"], pub)
        if pub["kind"] == protocol.KIND_CAPTURE_ANSWER:
            if pub["answer"]:
                self._finish(CAPTURE, POLICE,
                             f"claim confirmed at {pub['claim_cell']}")
            elif self.role == POLICE:
                # Denied: hard negative evidence - the thief is not on that cell.
                self.belief.exclude(tuple(pub["claim_cell"]), self.board)
        elif pub["kind"] == protocol.KIND_CAPTURED_EVENT:
            self._finish(CAPTURE, POLICE, pub["cause"])
        elif pub["kind"] == protocol.KIND_SURVIVAL_CLAIM:
            if pub["steps"] >= self.shared.survival_threshold and \
                    self.opp_steps + 1 >= pub["steps"]:
                self._finish(SURVIVAL, THIEF, f"survival at {pub['steps']} steps")
            else:
                self.declare_technical(self.other, "false survival claim")
        return {"ok": True}

    def process_reveal_response(self, resp: dict) -> None:
        for envelope in resp.get("events", []):
            self.on_event(envelope)
