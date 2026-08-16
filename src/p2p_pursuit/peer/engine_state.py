"""EngineState: per-sub-game state, records bookkeeping and view building.

The protocol handlers live in turn_engine.TurnEngine; this base class owns
everything they read and write, keeping each file within the size discipline.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..domain import protocol
from ..domain.belief import BeliefMap
from ..domain.board import Board, Cell
from ..domain.brains_base import BrainBase, BrainView, load_brain
from ..domain.rules import POLICE, THIEF
from ..domain.scent import ScentField
from ..domain.scoring import TECHNICAL_LOSS, ScoreTable
from ..domain.trust import TrustModel
from ..shared.config import PeerConfig, SharedConfig
from .state_machine import GamePhaseMachine


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class SubGameEnd:
    ending: str  # capture | survival | technical_loss
    winner: str  # police | thief | none
    cause: str


class EngineState:
    def __init__(self, role: str, shared: SharedConfig, peer: PeerConfig, *,
                 brain: BrainBase | None = None, talk: Any = None,
                 seed: int | None = None) -> None:
        self.role, self.shared, self.peer = role, shared, peer
        #: The role this peer was configured with. Under role alternation the
        #: role played in sub-game n is derived from it, never from whatever the
        #: previous sub-game happened to leave behind.
        self.natural_role = role
        self.other = THIEF if role == POLICE else POLICE
        # Which digest composition seals our records (RUNBOOK 3b): negotiated
        # per match, so an unmodified reference peer can audit us on its terms.
        self.commit_dialect = peer.interop_dialect
        self._injected_brain = brain
        self._brains: dict[str, BrainBase] = {}
        self.brain = self._brain_for(role)
        self.talk = talk
        self.rng = random.Random(seed)
        self.score_table = ScoreTable.from_config(shared.scoring)
        self.machine = GamePhaseMachine()
        self.tokens_used = 0
        self.sub_game = 0
        #: Frozen per-sub-game reveal, keyed by index and written exactly once.
        #: The live `my_records` is reset at every boundary, so the package we
        #: owe sub-game n has to be taken at the instant n ends - not read off a
        #: running engine minutes later, by which time the opponent's first turn
        #: of n+1 may already have moved us on. Never cleared by a boundary.
        self.audit_ledger: dict[int, dict[str, Any]] = {}
        self.start_sub_game(1)

    def _brain_for(self, role: str) -> BrainBase:
        """The brain for one side, built once and cached (roles may alternate)."""
        if self._injected_brain is not None:
            return self._injected_brain
        if role not in self._brains:
            spec = self.peer.strategy.get(
                "police_class" if role == POLICE else "thief_class")
            self._brains[role] = load_brain(spec, role)
        return self._brains[role]

    def set_role(self, role: str) -> None:
        """Swap sides for the next sub-game (role alternation, RUNBOOK 3b).

        Must be called *before* ``start_sub_game``, which reads the role to pick
        the starting cell, the opponent's start and the first mover.
        """
        self.role = role
        self.other = THIEF if role == POLICE else POLICE
        self.brain = self._brain_for(role)

    def begin_sub_game(self, n: int) -> None:
        """Enter sub-game ``n`` playing the role we owe it.

        The role has to be chosen BEFORE ``start_sub_game``, which reads it to
        pick both starting cells and the first mover. Doing that only in the
        series loop loses a race: the opponent starts its next sub-game as soon
        as it finishes the last one, so its first commit can arrive while we are
        still completing the audit exchange - and an inbound commit advances the
        sub-game too. Measured live 2026-08-01: we announced "playing as thief"
        and then played the sub-game out as police, which deadlocks both peers
        into a turn timeout. This is the one place the two steps are ordered.
        """
        if self.peer.alternate_roles:
            from .series_protocol import role_for

            role = role_for(self.natural_role, n)
            if role != self.role:
                self.set_role(role)
        self.start_sub_game(n)

    def start_sub_game(self, n: int) -> None:
        # Seal the outgoing sub-game's reveal before its records are wiped. A
        # boundary can be crossed by our own series loop OR by an inbound
        # message, and only one of those runs after `finish_sub_game` has taken
        # the package - so the freeze belongs here, not at the call site.
        self.freeze_audit()
        self.sub_game = n
        self.board = Board(self.shared.grid_size)
        self.own_pos: Cell = self.shared.cop_start if self.role == POLICE \
            else self.shared.thief_start
        opp_start = self.shared.thief_start if self.role == POLICE else self.shared.cop_start
        self.belief = BeliefMap.at(self.shared.grid_size, opp_start)
        self.own_field = ScentField(self.shared.grid_size, model=self.peer.scent_model)
        self.trust = TrustModel()
        self.my_steps = self.opp_steps = 0
        self.barriers_used = 0
        # Cleared with the rest of the board: a claim from an earlier sub-game
        # would make a later concession read as an answer to it, and skip the
        # corroboration that is the whole point of telling them apart.
        self.last_claim_cell: Cell | None = None
        self.next_mover = self.shared.first_mover
        self.end: SubGameEnd | None = None
        self.my_records: list[dict] = []
        self.my_hashes: list[str] = []
        self.opp_hashes: list[str] = []
        self.opp_public: list[dict | None] = []
        self.history: list[dict] = []  # interleaved {role, step, barrier} for audit timing
        self.hint_feed: list[dict] = []  # GUI: sent/received banter, local truth only
        self._pending_commit: str | None = None
        self.started_at = _now()
        self.opp_turn_times: list[str | None] = []
        self.machine.reset()

    @property
    def my_turn(self) -> bool:
        """Whose move it is, derived from the two step counts - never a flag.

        `next_mover` was a mutable flag written from two threads, and the two
        writes race: `_send_package` calls `link.reveal` OUTSIDE the lock, so the
        opponent's own reveal can arrive mid-flight, set the flag to us, and then
        be overwritten by our `sent_reveal()` setting it back to them. Both peers
        then wait for a move the other has already made, both 180 s timers run
        out, and the sub-game dies a technical loss - 0/0, and in a counted match
        sealed. Measured against orcai-mj 2026-08-13: their timer expired at step
        31 and so did ours, at identical step counts, twice.

        Counts cannot race like that. `my_steps` rises when we build a step and
        `opp_steps` when their reveal lands, so with the agreed first mover the
        owner of the turn is a pure function of both: the first mover is on turn
        when the counts are level, the second when it is one behind.
        """
        if self.end is not None:
            return False
        if self.role == self.shared.first_mover:
            return self.my_steps == self.opp_steps
        return self.my_steps < self.opp_steps

    def mark_started(self) -> None:
        """Start this sub-game's clock at the moment play does.

        `start_sub_game` runs from the constructor for sub-game 1, minutes
        before the handshake, so sub-game 1 otherwise reports a start time
        earlier than the declaration's. Guarded on nothing having been played,
        so re-entering a sub-game already in progress cannot rewind its clock.
        """
        if not self.my_records and not self.opp_hashes:
            self.started_at = _now()

    # -- the audit ledger ---------------------------------------------------
    def freeze_audit(self) -> dict[str, Any] | None:
        """Seal this sub-game's reveal into the ledger, once and for good.

        Called the moment the sub-game ends and again at the boundary, so the
        (payload, nonce) pairs we later reveal are literally the objects that
        produced the commitments we sent - copied, so nothing that arrives
        afterwards can edit them, and written once, so a late event cannot
        overwrite a package we have already handed out.
        """
        n = getattr(self, "sub_game", 0)
        if n <= 0 or not hasattr(self, "my_records") or n in self.audit_ledger:
            return self.audit_ledger.get(n)
        # Anything played counts, from either side: a sub-game where only the
        # opponent moved still has their commitments and their clock to preserve,
        # and gating on our own records alone loses both.
        if not (self.my_records or self.opp_hashes or self.end is not None):
            return None
        snapshot = {
            "sub_game": n,
            "role": self.role,
            "records": copy.deepcopy(self.my_records),
            "hashes": list(self.my_hashes),
            # What the opponent committed to *in play* here, so their reveal can
            # still be audited against the right sub-game when it arrives late.
            "opp_hashes": list(self.opp_hashes),
            # Frozen with the records, and for the same reason: the log is
            # written after the audit exchange, so reading the clock then would
            # time the paperwork rather than the sub-game.
            "started_at": self.started_at,
            "ended_at": _now(),
            "opp_turn_times": list(self.opp_turn_times),
        }
        self.audit_ledger[n] = snapshot
        return snapshot

    def opponent_hashes_for(self, n: int) -> list[str]:
        """Commitments the opponent sent us during sub-game ``n``."""
        if n == self.sub_game:
            return list(self.opp_hashes)
        snapshot = self.audit_ledger.get(n)
        return list(snapshot["opp_hashes"]) if snapshot else []

    def audit_snapshot(self, n: int | None = None) -> dict[str, Any]:
        """The frozen reveal for sub-game ``n`` (this one by default).

        Falls back to freezing now for a sub-game still in flight, so a caller
        can never be handed a *different* sub-game's records by accident.
        """
        n = self.sub_game if n is None else n
        if n == self.sub_game:
            self.freeze_audit()
        return self.audit_ledger.get(
            n, {"sub_game": n, "role": self.role, "records": [], "hashes": [],
                "opp_hashes": [], "started_at": self.started_at, "ended_at": None,
                "opp_turn_times": []})

    def _record(self, sealed: dict, commit_hash: str) -> dict:
        self.my_records.append(sealed)
        self.my_hashes.append(commit_hash)
        return protocol.public_view(sealed, commit_hash)

    def _note_opp(self, commit_hash: str, public: dict | None) -> None:
        self.opp_hashes.append(commit_hash)
        self.opp_public.append(public)

    def _view(self) -> BrainView:
        return BrainView(
            role=self.role, sub_game=self.sub_game, step=self.my_steps + 1,
            own_pos=self.own_pos, board=self.board, belief=self.belief,
            opp_scent=self._last_opp_scent(), own_scent=self.own_field.snapshot(),
            barriers_used=self.barriers_used, barrier_quota=self.shared.max_barriers,
            steps_remaining=self.shared.max_moves - self.my_steps,
            survival_threshold=self.shared.survival_threshold,
            trust=self.trust.value, map_area=self.shared.map_area, rng=self.rng,
            claim_enclosure=self.peer.claim_enclosure)

    def _last_opp_scent(self) -> list[list[float]]:
        for pub in reversed(self.opp_public):
            if pub and pub.get("kind") == protocol.KIND_STEP:
                return pub["scent"]
        return [[0.0] * self.shared.grid_size for _ in range(self.shared.grid_size)]

    def _make_hint(self, region: str) -> tuple[str, int]:
        from ..domain.hints import clip_words
        from ..strategy.talk_template import TemplateTalk

        every = max(1, self.peer.trash_talk_every_n_steps)
        if self.talk is None or ((self.my_steps + 1) % every and self.my_steps):
            return TemplateTalk().produce(region, self.shared.map_area,
                                          self.shared.hint_max_words, self.rng)
        text, tokens = self.talk.produce(region, self.shared.map_area,
                                         self.shared.hint_max_words, self.rng)
        return clip_words(text, self.shared.hint_max_words), tokens

    def declare_technical(self, offender: str, reason: str) -> None:
        if self.end is None:
            winner = THIEF if offender == POLICE else POLICE
            self.end = SubGameEnd(TECHNICAL_LOSS, winner, reason)
            self.machine.state = "TECHNICAL_LOSS"
            self.freeze_audit()

    def _finish(self, ending: str, winner: str, cause: str) -> None:
        if self.end is None:
            self.end = SubGameEnd(ending, winner, cause)
            self.freeze_audit()

    def sub_game_scores(self) -> tuple[int, int]:
        assert self.end is not None
        return self.score_table.score(self.end.ending)
