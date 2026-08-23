"""A thief whose *move* is proposed by an LLM, with the doctrine as the floor.

The mirror of :mod:`.police_llm`, and the guarantees in :mod:`.llm_move` are the
same ones. What differs is the evidence the prompt carries, because the thief
loses in a way the police does not: **87% of our archived thief deaths are
barrier kills**, and four of the eight in counted play were a barrier or an
enclosure. The doctrine cannot price that build - the reachable-region term has
spread 0 while a cage is going up, so every thief weight is a weight on nothing
until the last door closes and the number moves all at once.

So this prompt states the room explicitly: how many cells the thief can still
reach, how that has changed since last turn, and where every wall is. Whether a
model reads a half-built cage better than a term that cannot see it is exactly
the open question - and it is the one place in the turn loop where a model is
being asked something the tuned vector demonstrably cannot answer.

Off unless armed - see :mod:`.police_llm` for the two switches; the thief's are
``P2P_THIEF_CLASS`` and the same ``P2P_MOVE_PROVIDER``.
"""

from __future__ import annotations

from ..domain.board import target_of
from ..domain.brains_base import BrainView
from ..domain.rules import Decision
from .llm_move import LLMMove, MoveClient, bool_env, recent
from .pathing import bfs_distances
from .police_llm import cells, knowledge
from .thief_brain import ThiefBrain

EXAMPLES = """You are at [6, 4]. Step 12 of 35; survive 24 more steps to win.
You can currently reach 48 of the 48 open cells.
The opponent is provably on one of these cells: [4, 4].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [5, 4], cop 1 steps away, 3 exits, room 48
  E    -> you stand on [6, 5], cop 3 steps away, 2 exits, room 48
  W    -> you stand on [6, 3], cop 3 steps away, 3 exits, room 48
  STAY -> you stand on [6, 4], cop 2 steps away, 3 exits, room 48
MOVE: STAY

You are at [4, 5]. Step 7 of 35; survive 29 more steps to win.
You can currently reach 49 of the 49 open cells.
The opponent is provably on one of these cells: [3, 3].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [3, 5], cop 2 steps away, 4 exits, room 49
  S    -> you stand on [5, 5], cop 4 steps away, 4 exits, room 49
  E    -> you stand on [4, 6], cop 4 steps away, 3 exits, room 49
  W    -> you stand on [4, 4], cop 2 steps away, 4 exits, room 49
  STAY -> you stand on [4, 5], cop 3 steps away, 4 exits, room 49
MOVE: E

You are at [4, 6]. Step 8 of 35; survive 28 more steps to win.
You can currently reach 49 of the 49 open cells.
The opponent is provably on one of these cells: [3, 4].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [3, 6], cop 2 steps away, 3 exits, room 49
  S    -> you stand on [5, 6], cop 4 steps away, 3 exits, room 49
  W    -> you stand on [4, 5], cop 2 steps away, 4 exits, room 49
  STAY -> you stand on [4, 6], cop 3 steps away, 3 exits, room 49
MOVE: S

You are at [6, 6]. Step 10 of 35; survive 26 more steps to win.
You can currently reach 49 of the 49 open cells.
The opponent is provably on one of these cells: [4, 5].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [5, 6], cop 2 steps away, 3 exits, room 49
  W    -> you stand on [6, 5], cop 2 steps away, 3 exits, room 49
  STAY -> you stand on [6, 6], cop 3 steps away, 2 exits, room 49
MOVE: W"""

PROMPT = """You are the THIEF in a pursuit game on a {size}x{size} grid, \
rows and columns numbered 0-{last} from the top-left.

You are at {own}. Step {step} of {threshold}; survive {remaining} more steps to win.
Walls (impassable to both sides): {barriers}
The cop may still place {quota_left} more walls, one per turn, next to itself.
You can currently reach {room} of the {open_cells} open cells{trend}.
{knowledge}
{history}

What each legal move does, with distances measured AROUND the walls:
{table}

Surviving all {threshold} steps is worth 10 points and being caught is worth 5. \
You both move one cell per turn, so distance you take now is distance you keep.

{doctrine_of_the_turn}

The cop may only wall a cell it is standing next to, so any cell adjacent to the \
cop can be taken away from you next turn.

Here is how a tuned policy that survives this opponent 8 times out of 8 played \
five real positions:

{examples}

In THIS position that same policy would play {anchor}. It is very hard to beat, \
so play {anchor} unless you can say what it has missed - it cannot see a wall \
being built, and it cannot see that you have been shuffling between two cells.

Think it through in at most three short sentences, then finish with a final line \
of exactly "MOVE: X" where X is one of {moves}."""

#: The room number is a warning only while it is falling. Said unconditionally it
#: reads as "be cautious", and a thief that hedges against a cage nobody is
#: building simply gets run down: measured 2026-08-22, a prompt that always
#: mentioned the cage scored 10.00 against `najamjad-cage` - better than the
#: doctrine's 6.67 - while dropping `sniper` and `interceptor` from 10.00 to 5.00.
FLEE = ("Your room is not shrinking, so nothing is caging you yet: put distance "
        "between you and the cop. But distance alone walks you into a corner - "
        "measured 2026-08-22, a distance-greedy thief reached [6,6] in six moves "
        "and was run down there, while the tuned vector paced the edge and "
        "survived all 35. NEVER take a cell with 2 exits or fewer when one with "
        "3 or more is available, even if it is a step closer to the cop. Among "
        "cells with equal exits, take the larger distance.")
ESCAPE = ("Your room is FALLING - the cop is walling you in, and it wins that "
          "way just as surely as by catching you. Getting out matters more than "
          "one step of distance: take the move with the largest room, even if "
          "the cop gets closer.")

#: The variant that measured best of the thief prompts (still worse than the
#: vector). No examples, no anchor - see `_prompt` for why those are opt-in.
PLAIN_PROMPT = PROMPT.replace("""

Here is how a tuned policy that survives this opponent 8 times out of 8 played \
five real positions:

{examples}

In THIS position that same policy would play {anchor}. It is very hard to beat, \
so play {anchor} unless you can say what it has missed - it cannot see a wall \
being built, and it cannot see that you have been shuffling between two cells.
""", "")


class LLMThiefBrain(LLMMove, ThiefBrain):
    """The shipped thief, with the model given a veto over the movement."""

    def __init__(self, client: MoveClient | None = None, *,
                 only_when_caged: bool | None = None) -> None:
        super().__init__(client)
        self._prev_room: int | None = None
        #: Ask the model ONLY on the turns it is measurably better at.
        #:
        #: Five prompt versions and 32 live sub-games per version say the same
        #: thing: as a plain evader the model is far worse than the vector -
        #: 0/8 survivals against both `sniper` and `interceptor`, where the
        #: doctrine goes 8/8 - and it is *better* than the vector exactly once,
        #: while a cage is closing (`najamjad-cage` 7.50 against 6.88), which is
        #: the case the doctrine provably cannot price because region size has
        #: spread 0 during the build. So the model is asked when the room is
        #: falling and the doctrine plays otherwise. This also cuts the token
        #: bill by roughly the fraction of turns that are not a cage.
        self._only_when_caged = (bool_env("P2P_THIEF_LLM_ONLY_WHEN_CAGED", True)
                                 if only_when_caged is None else only_when_caged)

    def _pick_move(self, view: BrainView) -> Decision:
        # Captured BEFORE the doctrine runs: it sets both to ITS choice on the
        # way past, and `_run_len` is a count of repeats of a move we may be
        # about to discard. Line 157 of thief_brain reads both to decide a juke.
        prior_move, prior_run = self._last_move, self._run_len
        self.observe(view)
        fallback = super()._pick_move(view)
        legal = view.board.legal_moves(view.own_pos)
        room = self._room(view)
        if self._only_when_caged and not self._shrinking(room):
            self._settle(None)
            self._prev_room = room
            self.played.append(fallback.move)
            return fallback
        chosen = self.propose(self._prompt(view, legal, room, fallback.move), legal)
        self._settle(chosen)
        self._prev_room = room
        self.played.append(fallback.move if chosen is None else chosen)
        if chosen is None:
            return fallback
        self._run_len = prior_run + 1 if chosen == prior_move else 1
        self._last_move = chosen
        return Decision(move=chosen)

    @staticmethod
    def _room(view: BrainView) -> int:
        """Cells still reachable from where we stand - the cage, as one number."""
        return len(bfs_distances(view.board, view.own_pos))

    def _prompt(self, view: BrainView, legal: list[str], room: int,
                anchor: str) -> str:
        # Few-shot + anchor measured WORSE than history alone: -3.043 pts against
        # the vector at p=0.0005, versus -2.586 without them. Handed the vector's
        # own move and told to follow it, the model still overrode into a loss in
        # 15 of 16 discordant sub-games. Kept, opt-in, so the result is
        # reproducible rather than merely asserted.
        if not bool_env("P2P_THIEF_LLM_ANCHOR", False):
            return PLAIN_PROMPT.format(**self._fields(view, legal, room))
        return PROMPT.format(**self._fields(view, legal, room), anchor=anchor,
                             examples=EXAMPLES)

    def _fields(self, view: BrainView, legal: list[str], room: int) -> dict:
        size = view.board.size
        return {
            "size": size, "last": size - 1, "own": list(view.own_pos),
            "step": view.step, "threshold": view.survival_threshold,
            "remaining": view.steps_remaining,
            "barriers": cells(sorted(view.board.barriers)) or "none",
            "quota_left": max(0, view.barrier_quota - len(view.board.barriers)),
            "room": room, "open_cells": size * size - len(view.board.barriers),
            "trend": self._trend(room), "knowledge": knowledge(view),
            "history": recent(self.played, self.trail, self.seen, self.walls),
            "table": self._table(view, legal),
            "doctrine_of_the_turn": (ESCAPE if self._shrinking(room) else FLEE),
            "moves": ", ".join(legal),
        }

    def _shrinking(self, room: int) -> bool:
        """Is a cage actually closing? The warning is only true while it is."""
        return self._prev_room is not None and room < self._prev_room

    def _table(self, view: BrainView, legal: list[str]) -> str:
        """Each move's consequence: distance from the cop, and room left after it.

        Both numbers matter and they pull against each other - the step that
        gains a cell of distance is often the step into the pocket. Computing
        them here is what lets the model weigh the trade instead of estimating
        it from a wall list.
        """
        threat = view.opp_cells[0] if view.opp_cells else None
        rows = []
        for move in legal:
            landing = target_of(view.own_pos, move)
            reach = bfs_distances(view.board, landing)
            gap = "unknown" if threat is None else f"{reach.get(threat, 99)}"
            # `exits` is the doctrine's mobility term, spelled out. It is the
            # difference between a far cell and a far cell you cannot leave.
            exits = len(view.board.open_neighbors(landing))
            rows.append(f"  {move:<4} -> you stand on {list(landing)}, "
                        f"cop {gap} steps away, {exits} exits, room {len(reach)}")
        return "\n".join(rows)

    def _trend(self, room: int) -> str:
        """The direction of travel, which is the part a single number hides."""
        if self._prev_room is None or self._prev_room == room:
            return ""
        lost = self._prev_room - room
        if lost > 0:
            return f", down from {self._prev_room} last turn - you are being enclosed"
        return f", up from {self._prev_room} last turn"
