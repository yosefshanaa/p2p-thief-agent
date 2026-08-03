"""PeerRuntime: one autonomous peer over the network, end to end.

Handshake -> constitution/scent locks -> step-0 declaration -> series loop
(commit/reveal/claims via the opponent's tools) -> per-sub-game mutual audit
-> artifacts -> signed result -> Gatekeeper-guarded Gmail report
(the reporting half lives in runtime_reports).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from ..domain import negotiation
from ..domain.game_ids import make_game_id, new_game_uid
from ..infra.mcp_server import serve_in_thread, wait_until_up
from ..shared.config import load_role
from ..strategy.talk_llm import make_talk_provider
from . import runtime_reports
from .deadline import DeadlineExpiredError, DeadlineTracker
from .service import PeerService
from .turn_engine import TurnEngine
from .watchdog import Watchdog


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class PeerRuntime:
    def __init__(self, role: str, config_dir: Path, *, out_dir: Path = Path("results"),
                 seed: int | None = None, counted: bool = False,
                 prior_counted_games: int = 0, num_games: int | None = None) -> None:
        # `role` is this peer's NATURAL role; engine.role is what it plays right
        # now, which differs on even sub-games when roles alternate.
        self.role = self.natural_role = role
        self.counted = counted
        self.shared, self.peer = load_role(config_dir)
        talk = make_talk_provider(self.peer.trash_talk_provider, self.peer.llm_model,
                                  self.peer.llm_step_deadline_seconds,
                                  self.peer.llm_base_url)
        self.engine = TurnEngine(role, self.shared, self.peer, talk=talk, seed=seed)
        self.num_games = num_games or self.shared.num_games
        self.game_uid = new_game_uid()
        self.game_id = make_game_id(self.peer.group_id or "us", "opponent")
        self.out_dir = out_dir / f"{role}-{self.game_id}"
        handshake = negotiation.handshake_payload(
            self.shared, self.peer, role=role, game_id=self.game_id,
            game_uid=self.game_uid, counted=counted,
            prior_counted_games=prior_counted_games)
        self.service = PeerService(self.engine, handshake)
        net, rate = self.shared.network, self.shared.rate_limiter
        self.watchdog = Watchdog(timeout_sec=net.get("watchdog_timeout_sec", 60),
                                 on_freeze=self._persist_and_note)
        # A slow-but-alive link must not read as a frozen loop: the retry
        # budget outlasts the watchdog threshold, so beat on every attempt.
        self.deadline = DeadlineTracker(
            timeout_sec=net.get("response_timeout_sec", 30),
            max_retries=rate.get("max_retries", 3),
            backoff_sec=rate.get("retry_backoff_sec", 5),
            on_attempt=self.watchdog.beat)
        self.sub_results: list[dict[str, Any]] = []
        self.link: Any = None
        self.bridge: Any = None

    # -- lifecycle ----------------------------------------------------------
    def make_bridge(self, link: Any) -> Any:
        """Interop matches only: the translator that lets a reference peer play us."""
        from ..infra.interop_bridge import ReferenceBridge
        from ..infra.interop_codec import interop_identity, interop_terms
        from ..shared import sysinfo

        return ReferenceBridge(
            self.service, link, grid_size=self.shared.grid_size,
            terms=interop_terms(self.shared, num_games=self.num_games),
            identity=interop_identity(
                self.peer, mcp_url=f"http://0.0.0.0:{self.peer.my_port}/mcp",
                spec=sysinfo.collect()))

    def start_server(self) -> None:
        serve_in_thread(self.service, host="0.0.0.0", port=self.peer.my_port,
                        stateless=self.peer.stateless_http,
                        name=f"p2p-pursuit-{self.role}", bridge=self.bridge)
        _log(f"[{self.role}] FastMCP server on 0.0.0.0:{self.peer.my_port}"
             f"{' (+reference dialect)' if self.bridge else ''}")

    def attach(self, link: Any) -> Any:
        """Bind the outbound link, wrapping it in the interop bridge when this
        match is played in the reference dialect. Run before ``start_server``,
        so the server also answers the opponent's tool names."""
        if self.peer.interop_dialect == "reference":
            self.bridge = self.make_bridge(link)
            self.link = self.bridge
        else:
            self.link = link
        return self.link

    def connect(self, link: Any = None) -> bool:
        if link is not None or self.link is None:
            self.attach(link)
        link = self.link
        if not wait_until_up(link):
            _log(f"[{self.role}] opponent never came up at {self.peer.opponent_url}")
            return False
        theirs = self.deadline.call(link.handshake, self.service.my_handshake)
        self.service.their_handshake = theirs
        problems = negotiation.check_compatibility(
            self.service.my_handshake, theirs, num_games=self.num_games)
        if problems:
            for p in problems:
                _log(f"[{self.role}] REFUSING TO PLAY: {p}")
            return False
        runtime_reports.write_declaration(self, theirs)
        return True

    def _await_turn(self) -> bool:
        """Wait for the opponent's move, beating the watchdog in slices.

        The agreed turn timeout (180s) is longer than the watchdog threshold
        (60s), so waiting in one blocking call let the watchdog shut down a
        perfectly healthy peer whenever an opponent took over a minute -
        routine across a real tunnel, and a self-inflicted technical loss.
        Slicing keeps the watchdog's purpose intact: a genuinely frozen loop
        never reaches this code, so it still stops beating and is still caught.
        """
        slice_sec = max(1.0, self.watchdog.timeout_sec / 3)
        deadline = time.monotonic() + self.peer.turn_timeout_seconds
        while True:
            self.watchdog.beat()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self.service.wait_for_my_turn(min(slice_sec, remaining)):
                return True

    # -- one sub-game over the wire -----------------------------------------
    def play_sub_game(self, n: int) -> None:
        from . import series_protocol

        if not series_protocol.prepare_sub_game(self, n, _log):
            return
        self.service.ensure_sub_game(n)
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

    # -- series -------------------------------------------------------------
    def run_series(self) -> dict[str, Any]:
        self.watchdog.start()
        try:
            for n in range(1, self.num_games + 1):
                self.play_sub_game(n)
                self.sub_results.append(runtime_reports.finish_sub_game(self, n, _log))
        finally:
            self.watchdog.stop()
        return self.build_result()

    def build_result(self) -> dict[str, Any]:
        return runtime_reports.build_result(self)

    def report(self, result: dict[str, Any], transport: Any) -> dict[str, Any]:
        return runtime_reports.email_report(self, result, transport)

    def _persist_and_note(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        state = self.service.status()
        (self.out_dir / "watchdog_state.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8")
        _log(f"[{self.role}] WATCHDOG: main loop frozen; state persisted, shutting down")
