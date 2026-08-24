"""Playing one window: the sub-game loop and the audit package - as a mixin.

Split out of :mod:`.runtime` (§3.2, mixin strategy ch. 4.2). One concern: a
single sub-game from the role we hold in it, through to the package the mutual
audit needs. The series that drives the six windows, and the handshake that
precedes them, stay in :class:`~.runtime.PeerRuntime` and
:class:`~.runtime_connect.RuntimeConnect`.
"""

from __future__ import annotations

import sys
from typing import Any

from ..domain.scoring import TECHNICAL_LOSS
from .deadline import DeadlineExpiredError


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

class RuntimePlay:
    # -- one sub-game over the wire -----------------------------------------
    def play_window(self, n: int) -> None:
        """Play sub-game ``n``, re-offering it under its own number if it dies.

        A window that abandons before it was played is offered again rather
        than skipped, because a peer that re-offers and a peer that advances
        desynchronise permanently: their window 3 meets our window 5 and both
        guards refuse everything after. Only a *technical* ending re-offers - a
        capture or a survival is a window that was played, however badly.

        `window_reoffers` is 0 for every opponent that has not asked for this,
        which makes the loop a single pass and this method a no-op wrapper.
        """
        for attempt in range(self.peer.window_reoffers + 1):
            self.play_sub_game(n, renegotiate=attempt > 0)
            end = self.engine.end
            if end is None or end.ending != TECHNICAL_LOSS:
                return
            if attempt == self.peer.window_reoffers:
                _log(f"[{self.role}] sub-game {n} abandoned ({end.cause}) and the "
                     f"re-offer budget is spent; advancing")
                return
            _log(f"[{self.role}] sub-game {n} abandoned ({end.cause}); re-offering "
                 f"it under the same number ({attempt + 1}/{self.peer.window_reoffers})")
            with self.service.locked():
                self.engine.reoffer_sub_game(n)

    def play_sub_game(self, n: int, *, renegotiate: bool = False) -> None:
        from . import series_protocol

        # Role first (start_sub_game reads it), then reset onto this sub-game,
        # and only then re-negotiate: a refusal must be recorded against clean
        # state for THIS index, never against the previous sub-game's ending.
        series_protocol.take_role(self, n, _log)
        self.service.ensure_sub_game(n)
        # Clock starts here, before the per-sub-game re-handshake, so a sub-game
        # is timed including its own negotiation rather than from whenever the
        # engine object happened to be constructed.
        self.engine.mark_started()
        if not series_protocol.rehandshake_if_needed(self, n, _log,
                                                     force=renegotiate):
            return
        engine = self.engine
        while engine.end is None:
            self.watchdog.beat()
            if engine.my_turn:
                with self.service.locked():
                    package = engine.build_own_step()
                try:
                    self._send_package(package)
                except DeadlineExpiredError as exc:
                    with self.service.locked():
                        engine.declare_technical(engine.other, f"no response: {exc}")
            elif not self._await_turn():
                with self.service.locked():
                    engine.declare_technical(
                        engine.other, f"turn timeout ({self.peer.turn_timeout_seconds}s)")

    def _send_package(self, package: dict[str, Any]) -> None:
        engine, link = self.engine, self.link
        if "commit" in package:
            self.deadline.call(link.commit, package["commit"])
            with self.service.locked():
                engine.sent_commit()
            response = self.deadline.call(link.reveal, package["reveal"])
            with self.service.locked():
                engine.sent_reveal()
                engine.process_reveal_response(response)
        if package.get("event"):
            self.deadline.call(link.event, package["event"])
