"""EngineState: per-sub-game state, records bookkeeping and view building.

The protocol handlers live in turn_engine.TurnEngine; this base class owns
everything they read and write, keeping each file within the size discipline.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from ..domain import protocol
from ..domain.belief import BeliefMap
from ..domain.board import Board, Cell
from ..domain.brains_base import BrainBase, BrainView, load_brain
from ..domain.rules import POLICE, THIEF
from ..domain.scent import ScentField
from ..domain.scoring import TECHNICAL_LOSS, ScoreTable
from ..domain.tracking import OpponentTracker
from ..domain.trust import TrustModel
from ..shared.config import PeerConfig, SharedConfig
from .engine_audit import EngineAudit, _now
from .state_machine import GamePhaseMachine


@dataclass
class SubGameEnd:
    ending: str  # capture | survival | technical_loss
    winner: str  # police | thief | none
    cause: str


class EngineState(EngineAudit):
    def __init__(self, role: str, shared: SharedConfig, peer: PeerConfig, *,
                 brain: BrainBase | None = None, talk: Any = None,
                 seed: int | None = None) -> None:
        self.role, self.shared, self.peer = role, shared, peer
        #: The role this peer was configured with. Under role alternation the
        #: role played in sub-game n is derived from it, never from whatever the
        #: previous sub-game happened to leave behind.
        self.natural_role = role
        #: Correction to the sub-game index the alternation schedule is read
        #: from. Zero for every match that runs cleanly. It becomes 1 when the
        #: opponent's index has drifted from ours - a sub-game they abandoned
        #: and we did not, or the reverse - which makes `role_for` hand both
        #: peers the SAME role and turns every other sub-game into a technical
        #: loss. See `adopt_complementary_role`.
        self.role_offset = 0
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

    def role_for_sub_game(self, n: int) -> str:
        """The role the schedule owes sub-game ``n``, drift correction included.

        One place, because two callers reading the schedule with different
        corrections is the same desynchronisation this exists to repair.
        """
        from .series_protocol import role_for

        return role_for(self.natural_role, n + self.role_offset)

    def adopt_complementary_role(self, n: int) -> str:
        """Their index has drifted from ours: take the other side, permanently.

        Both peers derive their role from a sub-game index, so once the two
        indices disagree the roles collide - and they collide on EVERY
        subsequent sub-game of the same parity, which is why one abandoned
        sub-game has repeatedly taken a whole match with it. Measured across the
        archive: 10 sub-games ended "both peers claim role X", never as the first
        failure of a match and always after one.

        Correcting the *offset* rather than this one sub-game's role is what
        makes it stick. Flipping only the current role leaves the schedule
        drifted, so the next sub-game re-derives the colliding role and we are
        back where we started two turns later.
        """
        self.role_offset ^= 1
        # Set explicitly and enter through `start_sub_game`, NOT through
        # `begin_sub_game`. The latter re-derives the role from the schedule and
        # only when alternation is enabled on *this engine's* config, so relying
        # on it makes the adoption conditional on a flag that has nothing to do
        # with whether the two indices have drifted. The offset is still
        # corrected, so every later boundary that does re-derive stays aligned.
        self.set_role(THIEF if self.role == POLICE else POLICE)
        self.start_sub_game(n)
        return self.role

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
            role = self.role_for_sub_game(n)
            if role != self.role:
                self.set_role(role)
        self.start_sub_game(n)

    def reoffer_sub_game(self, n: int) -> None:
        """Re-enter sub-game ``n``, discarding the attempt that abandoned.

        For a peer that re-offers a failed window under its own number rather
        than advancing past it (`PeerConfig.window_reoffers`). Everything the
        attempt built is thrown away; only the index survives.

        The ledger eviction is the whole subtlety, and it has to happen in this
        order. `freeze_audit` is write-ONCE per index, and `start_sub_game`
        freezes on the way in - so the abandoned attempt seals itself under
        ``n`` before the reset, and a later `freeze_audit` for the replay finds
        ``n`` already present and silently keeps the failed one. We would then
        reveal an empty package for a sub-game we really played, which is a
        failed audit and a technical loss with no visible cause. Popping *after*
        `begin_sub_game` discards the corpse and leaves the index free for the
        replay to claim.
        """
        self.begin_sub_game(n)
        self.audit_ledger.pop(n, None)

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
        self.own_field = ScentField(
            self.shared.grid_size, model=self.peer.scent_model,
            serve_before_decay=self.peer.scent_serve_before_decay)
        # Fresh per sub-game, like the board: a fix carried across the boundary
        # would name a cell from a game that is already over.
        #
        # The tracker takes the same flag because the serve order is a *mutual*
        # term: whichever cut both sides agreed, both sides transmit. Passing it
        # to our field and not to the inverse would leave us reading their
        # packets against a physics neither of us plays.
        self.opp_tracker = OpponentTracker(
            self.shared.grid_size, self.peer.scent_model,
            serve_before_decay=self.peer.scent_serve_before_decay)
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

    def _view(self) -> BrainView:
        return BrainView(
            role=self.role, sub_game=self.sub_game, step=self.my_steps + 1,
            own_pos=self.own_pos, board=self.board, belief=self.belief,
            opp_scent=self._last_opp_scent(), own_scent=self.own_field.snapshot(),
            barriers_used=self.barriers_used, barrier_quota=self.shared.max_barriers,
            steps_remaining=self.shared.max_moves - self.my_steps,
            survival_threshold=self.shared.survival_threshold,
            trust=self.trust.value, map_area=self.shared.map_area, rng=self.rng,
            opp_cells=tuple(self.opp_tracker.possible(self.board)),
            opp_fix=self.opp_tracker.fix, opp_fix_lag=self.opp_tracker.lag,
            opp_lead=self.opp_tracker.projected(self.board),
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
