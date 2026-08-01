"""Thread-safe facade over the TurnEngine - the surface the MCP tools call.

The FastMCP server handles requests on its own threads; every entry locks
the engine, and the condition variable wakes the series runner when the
turn (or an audit package) arrives.
"""

from __future__ import annotations

import threading
from typing import Any

from . import audit_bridge
from .turn_engine import TurnEngine


class PeerService:
    def __init__(self, engine: TurnEngine, my_handshake: dict[str, Any]) -> None:
        self.engine = engine
        self.my_handshake = my_handshake
        self.their_handshake: dict[str, Any] | None = None
        self.audit_packages: dict[int, dict[str, Any]] = {}
        self.audit_verdicts: dict[int, dict[str, Any]] = {}
        self._cv = threading.Condition()

    # -- MCP tool surface ---------------------------------------------------
    def handshake(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._cv:
            self.their_handshake = payload
            self._cv.notify_all()
            return self.my_handshake

    def ensure_sub_game(self, n: int) -> None:
        with self._cv:
            if self.engine.sub_game < n:
                self.engine.begin_sub_game(n)

    def receive_commit(self, msg: dict[str, Any]) -> dict[str, Any]:
        with self._cv:
            if msg.get("sub_game", 0) > self.engine.sub_game:
                # Their commit can beat our own series loop to the boundary.
                self.engine.begin_sub_game(msg["sub_game"])
            return self.engine.on_commit(msg)

    def receive_reveal(self, pub: dict[str, Any]) -> dict[str, Any]:
        with self._cv:
            resp = self.engine.on_reveal(pub)
            self._cv.notify_all()
            return resp

    def receive_event(self, envelope: dict[str, Any]) -> dict[str, Any]:
        with self._cv:
            resp = self.engine.on_event(envelope)
            self._cv.notify_all()
            return resp

    def audit_exchange(self, package: dict[str, Any]) -> dict[str, Any]:
        """Store the opponent's sealed log, audit it, return our verdict of them."""
        with self._cv:
            n = package.get("sub_game", 0)
            self.audit_packages[n] = package
            verdict, violations = audit_bridge.run_audit(self.engine, package)
            self.audit_verdicts[n] = {"verdict": verdict, "violations": violations}
            self._cv.notify_all()
            return self.audit_verdicts[n]

    def health(self) -> dict[str, Any]:
        return {"ok": True, "role": self.engine.role, "sub_game": self.engine.sub_game}

    def status(self) -> dict[str, Any]:
        """Local-truth snapshot for the live GUI - never the opponent's position."""
        with self._cv:
            e = self.engine
            return {
                "role": e.role, "sub_game": e.sub_game, "phase": e.machine.state,
                "my_turn": e.my_turn, "own_pos": list(e.own_pos),
                "board_size": e.board.size,
                "barriers": sorted(list(b) for b in e.board.barriers),
                "belief": e.belief.snapshot(), "own_scent": e.own_field.snapshot(),
                "opp_scent": e._last_opp_scent(), "my_steps": e.my_steps,
                "opp_steps": e.opp_steps, "barriers_used": e.barriers_used,
                "trust": e.trust.value, "tokens_used": e.tokens_used,
                "hints": e.hint_feed[-8:],
                "end": None if e.end is None else
                {"ending": e.end.ending, "winner": e.end.winner, "cause": e.end.cause},
            }

    # -- runner-side waits --------------------------------------------------
    def wait_for_my_turn(self, timeout: float) -> bool:
        with self._cv:
            return self._cv.wait_for(
                lambda: self.engine.my_turn or self.engine.end is not None, timeout)

    def wait_for_handshake(self, timeout: float) -> bool:
        with self._cv:
            return self._cv.wait_for(lambda: self.their_handshake is not None, timeout)

    def wait_for_audit(self, sub_game: int, timeout: float) -> bool:
        with self._cv:
            return self._cv.wait_for(lambda: sub_game in self.audit_packages, timeout)

    def locked(self):
        return self._cv
