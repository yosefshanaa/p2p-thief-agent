"""TurnEngine: one peer's protocol handlers for a single sub-game.

Transport-agnostic and single-threaded: ``build_own_step`` produces the
outbound commit/reveal package; ``on_*`` handlers process inbound messages.
State and bookkeeping live in engine_state.EngineState.
"""

from __future__ import annotations

from typing import Any

from ..domain import protocol
from ..domain.belief import BeliefMap
from ..domain.board import Cell
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

__all__ = ["SubGameEnd", "TurnEngine"]


class TurnEngine(EngineState):
    # -- my move ------------------------------------------------------------
    def build_own_step(self) -> dict[str, Any]:
        """Produce this peer's next protocol package (step, or a forced event)."""
        self.machine.transition(COMPUTING_MOVE)
        if self.role == THIEF and self.board.is_enclosed(self.own_pos):
            return {"event": self._captured_event("enclosed")}
        view = self._view()
        decision = safe_decision(self.board, self.role, self.own_pos, self.barriers_used,
                                 self.shared.max_barriers, self.brain.decide(view))
        region, intent = self.brain.hint_plan(view, decision)
        hint, tokens = self._make_hint(region)
        self.tokens_used += tokens
        served = self.own_field.snapshot()
        pos_before = self.own_pos
        self.own_pos = apply_decision(self.board, self.own_pos, decision)
        if decision.barrier is not None:
            self.barriers_used += 1
        self.my_steps += 1
        self.own_field.emit(self.own_pos)
        self.own_field.decay()
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
        if self.role == POLICE and self.brain.should_claim(view, self.own_pos):
            # Claim rides inside the reveal: the answer returns atomically, no race.
            package["reveal"]["claim"] = {"cell": list(self.own_pos), "at_step": self.my_steps}
        if self.role == THIEF and self.my_steps >= self.shared.survival_threshold:
            package["event"] = self._survival_claim()
        return package

    def sent_commit(self) -> None:
        self.machine.transition(AWAITING_REVEAL)

    def sent_reveal(self) -> None:
        self.machine.transition(VERIFYING)
        self.machine.transition(WAITING_FOR_OPPONENT)
        self.next_mover = self.other

    def _seal_event(self, record: dict, ending: str, winner: str, cause: str) -> dict:
        """Seal a forced game event, log it and finish the sub-game."""
        sealed, h = seal(record, self.commit_dialect)
        public = self._record(sealed, h)
        self._finish(ending, winner, cause)
        return {"public": public, "hash": h}

    def _captured_event(self, cause: str) -> dict:
        return self._seal_event(
            protocol.captured_event_record(role=self.role, sub_game=self.sub_game,
                                           at_step=self.my_steps, cause=cause),
            CAPTURE, POLICE, cause)

    def _survival_claim(self) -> dict:
        return self._seal_event(
            protocol.survival_claim_record(role=self.role, sub_game=self.sub_game,
                                           steps=self.my_steps),
            SURVIVAL, THIEF, f"survived {self.my_steps} steps")

    # -- opponent's move ----------------------------------------------------
    def on_commit(self, msg: dict) -> dict:
        self._pending_commit = msg["hash"]
        return {"ack": True, "locked": True}

    def on_reveal(self, pub: dict) -> dict:
        """Process the opponent's public reveal; may return forced events (capture)."""
        self._note_opp(self._pending_commit or pub.get("hash", ""), pub)
        self._pending_commit = None
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
        if self.end is None:
            self._update_belief(pub)
        if self.end is None and pub.get("claim") and self.role == THIEF:
            events.append(self._answer_claim(pub["claim"]))
        self.next_mover = self.role
        return {"ok": True, "events": events}

    def _barrier_capture(self, cell: Cell) -> dict:
        return self._seal_event(
            protocol.captured_event_record(role=self.role, sub_game=self.sub_game,
                                           at_step=self.my_steps, cause="barrier"),
            CAPTURE, POLICE, f"barrier onto {cell}")

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

    # -- claims and events --------------------------------------------------
    def _answer_claim(self, claim: dict) -> dict:
        """Thief side: bound truthful answer (rule #21). The claim discloses the
        claimant's exact cell - our belief collapses to a delta there."""
        self.belief = BeliefMap.at(self.shared.grid_size, tuple(claim["cell"]))
        answer = list(self.own_pos) == list(claim["cell"])
        record = protocol.capture_answer_record(
            role=self.role, sub_game=self.sub_game, at_step=self.my_steps,
            claim_cell=tuple(claim["cell"]), answer=answer)
        sealed, h = seal(record, self.commit_dialect)
        public = self._record(sealed, h)
        if answer:
            self._finish(CAPTURE, POLICE, f"captured at {claim['cell']}")
        return {"public": public, "hash": h}

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
