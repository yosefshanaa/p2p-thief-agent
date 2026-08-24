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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..domain import negotiation
from ..domain.game_ids import (
    UNKNOWN_GROUP,
    make_game_id,
    new_game_uid,
    reference_game_id,
    reference_game_uid,
)
from ..domain.scoring import TECHNICAL_LOSS
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

    def connect(self, link: Any = None) -> bool:
        if link is not None or self.link is None:
            self.attach(link)
        link = self.link
        # A digest nobody can send is worse than no digest: it files
        # `confirmed: false` on a series that agreed perfectly, and the lecturer's
        # tooling reads that as a failed settlement. The whole consensus
        # transport - `submit_consensus`, `wait_for_consensus`, and the envelope
        # that rides the audit tool - lives on the reference bridge, and the
        # bridge is only built for the reference dialect. Found by playing two of
        # our own peers over real HTTP on `native` with consensus on: identical
        # digests on both sides, twelve `Verified OK` audits, and
        # `peer_consensus_sha: null` because there was no tool to carry it.
        #
        # Said out loud rather than fixed silently, because the honest repair is
        # to give the native dialect its own consensus tool, and shipping that
        # untested against a real peer would be the same mistake one layer down.
        if self.peer.series_consensus and self.bridge is None:
            _log(f"[{self.role}] WARNING: P2P_SERIES_CONSENSUS is on but the "
                 f"{self.peer.interop_dialect} dialect has no tool to exchange it - "
                 "the digest will be computed and filed, and `confirmed` will stay "
                 "false however well the series agrees. Play the reference dialect, "
                 "or set P2P_SERIES_CONSENSUS=false and settle by the per-sub-game "
                 "audits alone.")
        if not wait_until_up(link):
            _log(f"[{self.role}] opponent never came up at {self.peer.opponent_url}")
            return False
        # Before the handshake, not after: their backend merges it and then
        # needs it at every window boundary, so a Step-0 that arrives late is a
        # Step-0 that arrived after the crash it was meant to prevent.
        if self.peer.result_agreement:
            runtime_reports.send_step0(self, _log)
        # Reachable is not the same as ready: their tunnel can answer a tool
        # listing and their peer still be mid-restart when our handshake lands.
        try:
            theirs = self.deadline.call_within(
                link.handshake, self.service.my_handshake,
                budget_sec=self.peer.handshake_budget_sec,
                on_retry=lambda err: _log(
                    f"[{self.role}] handshake failed ({err}); retrying up to "
                    f"{self.peer.handshake_budget_sec}s"))
        except DeadlineExpiredError as exc:
            _log(f"[{self.role}] opponent never completed a handshake within "
                 f"{self.peer.handshake_budget_sec}s: {exc}")
            return False
        self.service.their_handshake = theirs
        self._adopt_shared_ids(theirs)
        self._join_at_their_index(theirs)
        problems = negotiation.check_compatibility(
            self.service.my_handshake, theirs, num_games=self.num_games)
        if problems:
            for p in problems:
                _log(f"[{self.role}] REFUSING TO PLAY: {p}")
            return False
        runtime_reports.write_declaration(self, theirs)
        return True

    def _join_at_their_index(self, theirs: dict[str, Any]) -> None:
        """Start the series where the opponent already is, not where we assume.

        Two peers that both advance on failure and both insist on their own index
        cannot resynchronise by restarting: whoever restarts is behind again by
        its own boot time, and the gap simply changes sign. Measured live against
        uoh-sqak 2026-08-10 - their peer moved 1 -> 3 in the two minutes ours took
        to come up, twice in a row.

        So a peer joining a series joins it where the other side is. Only forward:
        an index we have already settled is not replayable, and pulling the other
        peer backwards is what deadlocked both of us earlier tonight.

        **Never against a peer that serves a door per role.** uoh-sqak ran one
        process, so its index *was* the series position. A rule-1 split runs two,
        and each one reports the next window *it* will play - a cop that has
        played nothing truthfully declares `sub_game_number: 2`, because under
        alternation window 2 is its first. Read as a series position that says
        "window 1 is settled", and it is not: their thief is sitting on window 1
        waiting for us. We joined at 2 against yanell11 three times, skipped
        window 1, and then took their thief's window-1 turns for a role
        collision and retargeted onto the door of the half that was not playing
        - a permanent stall, every symptom of which we blamed on their state.
        Their two peers were correct throughout.

        We cannot repair that downstream: their turn messages carry no sub-game
        at all (`interop_codec.to_turn_message`), so a late window-1 turn is
        indistinguishable from a current one. Not skipping the window is the
        whole fix.
        """
        if getattr(self.peer, "opponent_doors", None):
            return
        declared = (theirs or {}).get("sub_game_number")
        if not isinstance(declared, int) or declared <= self.start_index:
            return
        if declared > self.num_games:
            _log(f"[{self.role}] opponent is on sub-game {declared}, past this "
                 f"series' {self.num_games} - refusing to join a finished series")
            return
        _log(f"[{self.role}] opponent is on sub-game {declared}; joining there "
             f"instead of {self.start_index} (they cannot replay what they settled)")
        self.start_index = declared

    def _adopt_shared_ids(self, theirs: dict[str, Any]) -> None:
        """Re-derive the game ids the way a reference-family peer does.

        Ours are minted in `__init__`, before the opponent's slug is known: the
        id carries a timestamp and a placeholder, and the uid is random. Both
        are fine for a match where each side files under its own id, and
        impossible for a *mutual* signature, whose first key is `game_id`.
        `make_game_id` stamps to the second, so two peers agree only when their
        clocks land in the same second - 1.5% of construction pairs inside one
        process, and never across two machines started minutes apart. The
        derived pair has no clock term: it comes from the agreed terms and the
        two slugs, so both peers reach it without exchanging it.

        The gate is knowing who the opponent is - not which dialect we speak,
        and not whether we asked for a consensus digest. Both narrower gates
        have been here. Dialect first, on the reasoning that a native match
        files under its own id: true of the *directory*, and beside the point
        for the document, since `mutual_signature` is written into every result
        we file. Then dialect-or-consensus, which fixed the pairing that could
        not confirm - two kit-built peers, twelve `Verified OK` audits, both
        sides agreeing the score, and `confirmed: false` on both. That still
        left the plain native match signing a document the opponent cannot
        reproduce, and it went unnoticed only because every opponent so far
        happens to speak the reference dialect.

        An *unknown* slug is a stop rather than a placeholder: deriving against
        "opponent" agrees with nobody while discarding the locally-unique pair
        we already hold. Safe to rebind either way - this runs after the
        handshake and before the first artifact is written.
        """
        from ..infra.interop_codec import interop_terms

        my_gid = self.peer.group_id or "us"
        their_gid = (theirs or {}).get("group_id") or ""
        if not their_gid or their_gid == UNKNOWN_GROUP:
            _log(f"[{self.role}] opponent sent no group_id; keeping our own "
                 f"{self.game_id} / {self.game_uid}. Both are locally minted, so "
                 "`mutual_signature` will differ from theirs however well the "
                 "series agrees.")
            return
        terms = interop_terms(self.shared, num_games=self.signed_num_games)
        # A mutually agreed label replaces the derived id when both teams set the
        # same one. It is a top-level key of the consensus object, so an override
        # on one side only is a guaranteed digest mismatch - which is why it is an
        # explicit per-match value rather than anything inferred. The uid follows
        # it: a label that reached the id and not the uid would give two labelled
        # series between the same two teams one uid, so the label is folded in
        # whenever we set one - and only then, leaving every unlabelled pairing
        # on the byte-identical seed it already agreed.
        self.game_id = self.peer.game_id_label or reference_game_id(my_gid, their_gid)
        self.game_uid = reference_game_uid(
            terms, my_gid, their_gid,
            game_id=self.game_id if self.peer.game_id_label else "")
        # Their `game_id` is deterministic by design - the same two teams always
        # derive the same string - so it cannot also name our output directory:
        # a warm-up would overwrite the sealed logs of the counted match played
        # against the same opponent, which are the one artifact we must be able
        # to produce afterwards. Filenames keep the agreed id (Appendix F); only
        # the containing directory is made unique.
        self.out_dir = self._out_root / f"{self.role}-{self.game_id}-{self._run_stamp}"
        self.service.my_handshake["game_id"] = self.game_id
        self.service.my_handshake["game_uid"] = self.game_uid
        _log(f"[{self.role}] shared ids adopted: {self.game_id} / {self.game_uid}")

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
                self.series_consensus = runtime_reports.exchange_series_consensus(self, _log)
            # After the consensus exchange, because the two are different digests
            # over different scopes and their §5 says so explicitly:
            # `result_sha256` is NOT `series_consensus_sha256` and they are never
            # aliased. This one is what makes their side able to file at all.
            if self.peer.result_agreement:
                self.result_agreement = runtime_reports.exchange_result_agreement(
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
