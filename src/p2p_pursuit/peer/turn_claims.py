"""Claims and terminal events: how a sub-game ends, and how we answer a claim.

Split out of :mod:`.turn_engine` (§3.2, mixin strategy ch. 4.2). One concern:
every path by which a sub-game reaches an ending - landing on the thief, a
barrier placed onto it (#46), an enclosure with no legal move (#47), survival
to the threshold - plus the truthful answer we owe an opponent's capture claim
(#21). The turn loop itself stays in :class:`~.turn_engine.TurnEngine`.
"""

from __future__ import annotations

from ..domain import protocol
from ..domain.belief import BeliefMap
from ..domain.board import Cell
from ..domain.crypto import seal
from ..domain.rules import POLICE, THIEF
from ..domain.scoring import CAPTURE, SURVIVAL

#: Below this the opponent's trail is too faint to name the cell we would be
#: claiming, and an enclosure claim has to name one.
ENCLOSURE_SCENT_MIN = 0.7

class TurnClaims:
    def _seal_event(self, record: dict, ending: str, winner: str, cause: str) -> dict:
        """Seal a forced game event, log it and finish the sub-game."""
        sealed, h = seal(record, self.commit_dialect)
        public = self._record(sealed, h)
        self._finish(ending, winner, cause)
        return {"public": public, "hash": h}

    def _enclosed_opponent(self) -> Cell | None:
        """The thief's cell, if our barriers have left it no legal move (book 3.4).

        A native peer confesses this itself, but a foreign implementation simply
        holds and plays on: we squeezed the reference peer into a corner on turn
        12 of a live match, sealed both its exits, and then lost the sub-game to
        "survival" 23 turns later. The police must therefore claim the enclosure.

        The claim is independently checkable rather than taken on trust: barrier
        placements are public and truthful by rule, and the opponent's own signed
        log reveals where it stood, so the audit can confirm both halves - which
        is exactly why the cell has to be *right*. Naming it by the scent
        argmax was unsound: on the played archive that argmax is the emitter's
        cell 11% of the time (the field saturates and ties), so a top-left cell
        that our own barriers happened to seal would have been claimed as an
        enclosure while the thief ran free elsewhere - a false claim, in a
        record the opponent audits. The tracker's fix is exact or absent.
        """
        cells = self.opp_tracker.possible(self.board)
        if not cells:
            # No fix yet (fewer than two served fields). The argmax is only
            # sound while the field is still sparse, which is exactly then.
            scent = self._last_opp_scent()
            if not scent or max(max(row) for row in scent) < ENCLOSURE_SCENT_MIN:
                return None
            size = self.board.size
            cells = [max(((r, c) for r in range(size) for c in range(size)),
                         key=lambda p: scent[p[0]][p[1]])]
        # With a lagged fix the thief may be on any of a few cells; claiming an
        # enclosure means claiming it cannot move, so every candidate has to be
        # enclosed before the claim is honest. In practice a cell is enclosed
        # only when its neighbours are barred, which collapses the set anyway.
        enclosed = [c for c in cells if self.board.is_open(c) and self.board.is_enclosed(c)]
        return enclosed[0] if len(enclosed) == len(cells) == 1 else None

    def _enclosure_claim(self, cell: Cell) -> dict:
        return self._seal_event(
            protocol.captured_event_record(role=self.role, sub_game=self.sub_game,
                                           at_step=self.my_steps, cause=f"enclosed at {cell}"),
            CAPTURE, POLICE, f"enclosed at {cell}")

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

    def _barrier_capture(self, cell: Cell) -> dict:
        return self._seal_event(
            protocol.captured_event_record(role=self.role, sub_game=self.sub_game,
                                           at_step=self.my_steps, cause="barrier"),
            CAPTURE, POLICE, f"barrier onto {cell}")

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
