"""PeerRuntime: one autonomous peer over the network, end to end.

Handshake -> constitution/scent locks -> step-0 declaration -> series loop
(commit/reveal/claims via the opponent's tools) -> per-sub-game mutual audit
-> artifacts -> signed result -> Gatekeeper-guarded Gmail report
(the reporting half lives in runtime_reports).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..domain import negotiation
from ..domain.game_ids import (
    UNKNOWN_GROUP,
    make_game_id,
    new_game_uid,
)
from ..infra.mcp_server import serve_in_thread
from ..shared.config import load_role
from ..strategy.talk_llm import make_talk_provider
from . import report_agreement, report_consensus, runtime_reports
from .deadline import DeadlineTracker
from .runtime_connect import RuntimeConnect
from .runtime_play import RuntimePlay
from .service import PeerService
from .turn_engine import TurnEngine
from .watchdog import Watchdog


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class PeerRuntime(RuntimePlay, RuntimeConnect):
    def __init__(self, role: str, config_dir: Path, *, out_dir: Path = Path("results"),
                 seed: int | None = None, counted: bool = False,
                 prior_counted_games: int = 0, num_games: int | None = None) -> None:
        # `role` is this peer's NATURAL role; engine.role is what it plays right
        # now, which differs on even sub-games when roles alternate.
        self.role = self.natural_role = role
        self.counted = counted
        self.prior_counted_games = prior_counted_games
        self.shared, self.peer = load_role(config_dir)
        talk = make_talk_provider(self.peer.trash_talk_provider, self.peer.llm_model,
                                  self.peer.llm_step_deadline_seconds,
                                  self.peer.llm_base_url)
        self.engine = TurnEngine(role, self.shared, self.peer, talk=talk, seed=seed)
        self.num_games = num_games or self.shared.num_games
        #: What the *terms* say the series is, which `--games` must not move: a
        #: short compatibility run plays fewer sub-games by mutual agreement and
        #: still signs the agreed length. Signing the short count instead fails
        #: the peer's terms comparison on the one run meant to prove they agree.
        self.signed_num_games = self.peer.signed_num_games or self.num_games
        self.game_uid = new_game_uid()
        self.game_id = make_game_id(self.peer.group_id or "us", UNKNOWN_GROUP)
        self._out_root = out_dir
        #: Distinguishes two runs against the same opponent; see `_adopt_shared_ids`.
        self._run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
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
        #: Where this peer joins the series - 1 unless the opponent is already
        #: further on; see `_join_at_their_index`.
        self.start_index = 1
        self.sub_results: list[dict[str, Any]] = []
        self.link: Any = None
        self.bridge: Any = None
        #: The step-0 declaration as filed, kept so its `ended_at` can be
        #: stamped and the document re-sealed when the series finishes.
        self.declaration: dict[str, Any] | None = None
        #: The §10.3 exchange's outcome, or None when the opponent's contract
        #: does not specify one - absent from the result rather than a false
        #: "unconfirmed" against every peer that never agreed to send a digest.
        self.series_consensus: dict[str, Any] | None = None
        self.result_agreement: dict[str, Any] | None = None

    # -- lifecycle ----------------------------------------------------------
    def make_bridge(self, link: Any) -> Any:
        """Interop matches only: the translator that lets a reference peer play us."""
        from ..infra.interop_bridge import ReferenceBridge
        from ..infra.interop_codec import interop_identity, interop_terms
        from ..shared import sysinfo

        return ReferenceBridge(
            self.service, link, grid_size=self.shared.grid_size,
            terms=interop_terms(self.shared, num_games=self.signed_num_games),
            identity=interop_identity(
                self.peer, mcp_url=f"http://0.0.0.0:{self.peer.my_port}/mcp",
                spec=sysinfo.collect(),
                counted_games_played=self.prior_counted_games,
                public_doors=self.peer.public_doors),
            runtime=self)

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

    # -- series -------------------------------------------------------------
    def run_series(self) -> dict[str, Any]:
        self.watchdog.start()
        try:
            for n in range(self.start_index, self.num_games + 1):
                self.play_window(n)
                self.sub_results.append(runtime_reports.finish_sub_game(self, n, _log))
            # The watchdog guards the *turn* loops, which are the only places
            # that beat. The consensus linger deliberately blocks for up to
            # `consensus_wait_sec` (600s against yanell11) with nothing to beat,
            # against a 60s watchdog - so leaving it armed here fires a false
            # "main loop frozen" on every clean series that waits out a peer
            # which has already gone. It cost us a real diagnosis: we read that
            # line as a hang, killed the process four minutes before
            # `wait_for_consensus` would have returned, and lost the result
            # artifact it was about to file. The wait is bounded by its own
            # timeout, so nothing here can hang unguarded.
            self.watchdog.stop()
            if self.peer.series_consensus:
                self.series_consensus = report_consensus.exchange_series_consensus(self, _log)
            # After the consensus exchange, because the two are different digests
            # over different scopes and their §5 says so explicitly:
            # `result_sha256` is NOT `series_consensus_sha256` and they are never
            # aliased. This one is what makes their side able to file at all.
            if self.peer.result_agreement:
                self.result_agreement = report_agreement.exchange_result_agreement(
                    self, _log)
        finally:
            self.watchdog.stop()
            # After the last sub-game and the consensus exchange, so the filed
            # declaration times the match rather than the paperwork - and inside
            # `finally`, so a series cut short still records when it stopped.
            runtime_reports.close_declaration(self)
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
        # NOT a shutdown: `on_freeze` persists and returns, the watchdog thread
        # exits, and the main loop keeps running. Saying otherwise sent us
        # hunting a hang that was a bounded wait doing its job.
        _log(f"[{self.role}] WATCHDOG: no heartbeat for {self.watchdog.timeout_sec}s; "
             f"state persisted to watchdog_state.json (the main loop is NOT killed)")
