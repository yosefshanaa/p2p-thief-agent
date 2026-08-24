"""Shared machinery for a brain that lets a model propose its move.

Both roles need exactly the same four guarantees, and the guarantees are the
whole reason this is allowed to exist, so they live in one place rather than in
two copies that can drift apart:

* the doctrine move is computed first, every turn, and is what plays unless a
  *legal* alternative comes back inside the deadline;
* one bounded call per turn, a third of the step envelope, no retries;
* three consecutive failures and the model is off for the rest of the process;
* every token spent deciding is handed to the turn engine for the budget seal.

The role modules add only the prompt and the state their parent brain keeps.
See :mod:`.police_llm` and :mod:`.thief_llm`.
"""

from __future__ import annotations

import os
import time

from .llm_client import (
    COMPLETION_BUDGET,
    FAILURES_BEFORE_GIVING_UP,
    MOVE_PROVIDERS,
    MoveClient,
    bool_env,
    int_env,
)

__all__ = ["COMPLETION_BUDGET", "FAILURES_BEFORE_GIVING_UP", "MOVE_PROVIDERS",
           "LLMMove", "MoveClient", "bool_env", "final_move", "first_legal",
           "int_env", "recent"]


class LLMMove:
    """Mixin: the client, the circuit breaker, the meter and the veto.

    Mixed in *before* the doctrine brain so ``super()`` in a role hook still
    reaches the tuned implementation.
    """

    def __init__(self, client: MoveClient | None = None) -> None:
        super().__init__()
        provider = (os.environ.get("P2P_MOVE_PROVIDER")
                    or os.environ.get("P2P_TRASH_TALK_PROVIDER") or "").strip().lower()
        model = (os.environ.get("P2P_MOVE_MODEL") or "").strip()
        deadline = int_env("P2P_STEP_DEADLINE_SECONDS", 30)
        # A third of the envelope, the same slice the banter provider takes -
        # both can run in one turn and the turn still has to land.
        timeout = max(3, deadline // 3)
        self._client = client if client is not None else (
            MoveClient(provider, model, timeout,
                       (os.environ.get("P2P_LLM_BASE_URL") or "").strip())
            if provider in MOVE_PROVIDERS else None)
        self.samples = max(1, int_env("P2P_MOVE_SAMPLES", 1))
        self._tokens = 0
        self._failures = 0
        #: Turns each side actually decided, for the match report and the log.
        self.moves_from_model = 0
        self.moves_from_doctrine = 0
        #: WHY we fell back, because the three causes need different fixes: a
        #: prompt that produces illegal moves is ours to rewrite, a call that
        #: raises is infrastructure, and a cold or broken-off client is neither.
        self.spent_total = 0
        self.fallbacks = {"call_failed": 0, "illegal_reply": 0, "not_live": 0}
        self.last_error = ""
        #: What we actually played, most recent last. A model with no memory of
        #: its own last moves oscillates - two cells, forever - because every
        #: turn looks like a fresh decision from a symmetric position.
        self.played: list[str] = []
        #: Cells WE have stood on, and cells we have SEEN the opponent on. Every
        #: call is a fresh stateless completion, so anything not written into the
        #: prompt does not exist for the model. A move list alone is not enough:
        #: "S, E, STAY, STAY" cannot tell it that it has been parked in a corner
        #: for four turns, which is the failure the live archive actually shows.
        self.trail: list = []
        self.seen: list = []
        #: Barriers in the ORDER they appeared. As an unordered set three walls
        #: are scenery; in sequence down one column they are a cage being built,
        #: which is the one thing the tuned vector provably cannot price.
        self.walls: list = []
        self._known_walls: set = set()

    def observe(self, view) -> None:
        """Record this turn's board before deciding. Cheap, and pure bookkeeping."""
        self.trail.append(view.own_pos)
        if view.opp_cells:
            self.seen.append(view.opp_cells[0])
        fresh = [cell for cell in view.board.barriers if cell not in self._known_walls]
        # Sorted so a turn that reveals two at once is still deterministic.
        for cell in sorted(fresh):
            self._known_walls.add(cell)
            self.walls.append((view.step, cell))

    def take_tokens(self) -> int:
        """Hand the turn engine what this brain spent, and reset. Metered once."""
        spent, self._tokens = self._tokens, 0
        return spent

    @property
    def live(self) -> bool:
        if self._client is None or self._failures >= FAILURES_BEFORE_GIVING_UP:
            return False
        # An `openai` client warms on a background thread; until it lands the
        # doctrine plays. A test double has no `ready` and is live immediately.
        return getattr(self._client, "ready", True)

    def propose(self, prompt: str, legal: list[str]) -> str | None:
        """A legal move the model settled on, or None - which means fall back.

        With ``P2P_MOVE_SAMPLES`` above 1 the same prompt is asked that many
        times and the majority answer wins (self-consistency). It costs N times
        the tokens and only helps if the model's errors are *variance*; a
        systematic preference survives a vote intact.
        """
        if self.samples > 1:
            votes: dict[str, int] = {}
            for _ in range(self.samples):
                one = self._ask_once(prompt, legal)
                if one is not None:
                    votes[one] = votes.get(one, 0) + 1
            if not votes:
                return None
            top = max(votes.values())
            winners = sorted(m for m, n in votes.items() if n == top)
            # A split vote is the model telling us it does not know; the tuned
            # vector is a better tie-break than an arbitrary one of its guesses.
            return winners[0] if len(winners) == 1 else None
        return self._ask_once(prompt, legal)

    def _ask_once(self, prompt: str, legal: list[str]) -> str | None:
        if not self.live:
            self.fallbacks["not_live"] += 1
            return None
        started = time.monotonic()
        try:
            text, tokens = self._client.ask(prompt)
            self._tokens += tokens
            self.spent_total += tokens
        except Exception as exc:  # noqa: BLE001 - any failure at all is a fallback
            # The breaker exists to stop us paying a timeout every turn for an
            # endpoint that is gone - so only a failure that COST TIME trips it.
            # Measured 2026-08-22: 20 instant `empty completion` errors tripped
            # it three-in-a-row and cost 103 further turns to `not_live`, five
            # times the damage of the failures themselves. A fast failure is
            # one turn's fallback and nothing more.
            if time.monotonic() - started >= getattr(self._client, "timeout", 10) / 2:
                self._failures += 1
            self.fallbacks["call_failed"] += 1
            self.last_error = f"{type(exc).__name__}: {exc}"[:160]
            return None
        self._failures = 0
        # `final_move`, not `first_legal`: the prompt now lets the model reason,
        # and a reasoning reply names the moves it REJECTS before its choice.
        chosen = final_move(text, legal)
        if chosen is None:
            self.fallbacks["illegal_reply"] += 1
            self.last_error = f"unusable reply: {text[:80]!r} (legal: {legal})"
        return chosen

    def _settle(self, chosen: str | None) -> None:
        """Count who decided this turn: the model, or the vector it overrides."""
        if chosen is None:
            self.moves_from_doctrine += 1
        else:
            self.moves_from_model += 1


def recent(played: list[str], trail: list, seen: list, walls: list,
           keep: int = 8) -> str:
    """Everything the model would otherwise have no way to know it knows.

    Each call is stateless, so history is not "extra context" - it is the whole
    difference between a policy and a reflex. Three separate things go in, and
    each answers a question the current board cannot:

    * where WE have been - a corner you have sat in for four turns looks
      identical, from one board, to a corner you just reached;
    * where the OPPONENT has been - its direction of travel, which is the most
      useful single fact in a pursuit and is invisible in a position;
    * the ORDER walls appeared - a cage under construction versus scenery.
    """
    lines = []
    # `observe` runs before the prompt is built, so the trail already holds this
    # turn's cell - "first move" is one entry, not zero.
    if len(trail) > 1:
        path = " -> ".join(str(list(c)) for c in trail[-keep:])
        lines.append(f"Your path so far (oldest first): {path}.")
        if played:
            lines.append(f"The moves that made it: {', '.join(played[-keep:])}.")
        tail = trail[-4:]
        if len(tail) == 4 and len({tuple(c) for c in tail}) <= 2:
            lines.append("WARNING: you have been shuffling between the same two "
                         "cells - you are not escaping, you are waiting to be caught.")
    else:
        lines.append("This is your first move.")
    if len(seen) >= 2:
        path = " -> ".join(str(list(c)) for c in seen[-keep:])
        lines.append(f"Where the opponent has been (oldest first): {path}.")
    if walls:
        laid = ", ".join(f"{list(cell)} at step {step}" for step, cell in walls[-6:])
        lines.append(f"Walls in the order they appeared: {laid}. "
                     f"Walls going up in a line are a cage being built - look at "
                     f"which side of you they are on.")
    return "\n".join(lines)


def first_legal(text: str, legal: list[str]) -> str | None:
    """The first legal move named anywhere in the reply, or None.

    Deliberately lenient about surrounding prose and strict about the token: a
    model that answers "I'll go NORTH" has still named a move, while one that
    answers "NORTHEAST" has not named a legal one and must not be coerced into
    the nearest match.

    Only safe while the reply is a bare token. Once the model is allowed to
    reason out loud it will mention moves it is rejecting, and the FIRST one is
    then the wrong answer - use `final_move`.
    """
    words = {w.strip(".,:;!?\"'*`") for w in text.upper().split()}
    for move in legal:                      # legal order, so ties are not textual
        if move in words:
            return move
    return None


def final_move(text: str, legal: list[str]) -> str | None:
    """The move a *reasoning* reply settles on, or None.

    Three readings, in order of how much they can be trusted:

    1. an explicit ``MOVE: X`` marker, which is what the prompt asks for;
    2. failing that, the LAST legal token mentioned - a model that reasons names
       the moves it rejects first and its choice last, so `first_legal` would
       systematically return a rejected move;
    3. failing that, nothing, and the doctrine plays.
    """
    upper = text.upper()
    for line in reversed(upper.splitlines()):
        if "MOVE:" in line:
            tail = line.split("MOVE:", 1)[1]
            named = [m for m in legal if m in
                     {w.strip(".,:;!?\"'*`") for w in tail.split()}]
            if named:
                # Longest first so STAY is not shadowed by a substring match.
                return max(named, key=len)
    words = [w.strip(".,:;!?\"'*`") for w in upper.split()]
    for word in reversed(words):
        if word in legal:
            return word
    return None
