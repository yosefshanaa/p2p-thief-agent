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
from ..domain.trust import TrustModel
from ..shared.config import PeerConfig, SharedConfig
from .state_machine import GamePhaseMachine


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
        self.next_mover = self.shared.first_mover
        self.end: SubGameEnd | None = None
        self.my_records: list[dict] = []
        self.my_hashes: list[str] = []
        self.opp_hashes: list[str] = []
        self.opp_public: list[dict | None] = []
        self.history: list[dict] = []  # interleaved {role, step, barrier} for audit timing
        self.hint_feed: list[dict] = []  # GUI: sent/received banter, local truth only
        self._pending_commit: str | None = None
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

    def _finish(self, ending: str, winner: str, cause: str) -> None:
        if self.end is None:
            self.end = SubGameEnd(ending, winner, cause)

    def sub_game_scores(self) -> tuple[int, int]:
        assert self.end is not None
        return self.score_table.score(self.end.ending)
