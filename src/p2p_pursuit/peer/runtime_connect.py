"""Getting two peers agreed and aligned before a ball is kicked - as a mixin.

Split out of :mod:`.runtime` (§3.2, mixin strategy ch. 4.2). One concern: the
handshake. Reaching the opponent, negotiating the constitution, adopting the
shared game ids in whichever dialect we settled on, joining a peer that is
already several windows in, and waiting for our turn. Playing the windows stays
in :class:`~.runtime.PeerRuntime`.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from ..domain import negotiation
from ..domain.game_ids import (
    UNKNOWN_GROUP,
    reference_game_id,
    reference_game_uid,
)
from ..infra.mcp_server import wait_until_up
from . import report_consensus, report_step0, runtime_reports
from .deadline import DeadlineExpiredError


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

class RuntimeConnect:
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
            # Step-0 must name THIS game: their runtime refuses a declaration
            # carrying ids it does not recognise, by design, since a Step-0 for
            # another game would bind the wrong declaration. Both ids are pure
            # functions of the agreed terms and the two slugs, so a configured
            # opponent slug lets us derive the agreed pair before any handshake
            # has happened. Without one this is a no-op and Step-0 goes out
            # locally minted - which is the E-PROTO-STALE of 2026-08-24.
            if report_consensus.their_group_id_hint():
                self._adopt_shared_ids({})
            report_step0.send_step0(self, _log)
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
        from .report_consensus import their_group_id_hint

        their_gid = (theirs or {}).get("group_id") or their_group_id_hint() or ""
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
