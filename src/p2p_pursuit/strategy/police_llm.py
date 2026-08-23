"""A police whose *move* is proposed by an LLM, with the doctrine as the floor.

Every other module in this package decides a move in pure Python, and
:mod:`.talk_llm` states the reason in one line - "the move is decided before any
of this runs" - because a model on the turn path can stall, and a stalled turn
is a forfeited sub-game rather than a slow one. This module crosses that line
for one role; :mod:`.llm_move` carries the guarantees that make it survivable,
and what is left here is the prompt and the bookkeeping.

**Barriers stay with the doctrine.** 87% of our archived thief kills are barrier
kills and the placement logic is the searched part of the vector, so a turn the
doctrine wants to spend on a barrier is never offered to the model. Set
``P2P_POLICE_LLM_BARRIERS=true`` to hand those over as well.

Off unless asked for: `load_brain` reads ``[strategy] police_class``, commented
out in every shipped `game.toml`. Arm it for one match with
``P2P_POLICE_CLASS=p2p_pursuit.strategy.police_llm:LLMPoliceBrain`` plus a
``P2P_MOVE_PROVIDER``, rather than by editing the committed file - an edit rides
silently into the next opponent's match.
"""

from __future__ import annotations

from ..domain.board import target_of
from ..domain.brains_base import BrainView
from ..domain.rules import Decision
from .llm_move import LLMMove, MoveClient, bool_env, recent
from .pathing import bfs_distances
from .police_brain import PoliceBrain

PROMPT = """You are the COP in a pursuit game on a {size}x{size} grid, \
rows and columns numbered 0-{last} from the top-left.

You are at {own}. Step {step} of {threshold}; {remaining} steps remain.
Walls (impassable to both sides): {barriers}
Barriers you may still place: {quota_left}
{knowledge}
{history}

What each legal move does, with distances measured AROUND the walls:
{table}

Capturing is worth 20 points and letting the thief survive is worth 5, so close \
the distance. You both move one cell per turn and the thief moves too, so a move \
that only keeps pace never catches it. Answer with EXACTLY ONE of {moves} and \
nothing else."""


class LLMPoliceBrain(LLMMove, PoliceBrain):
    """The shipped police, with the model given a veto over the movement only."""

    def __init__(self, client: MoveClient | None = None, *,
                 allow_barriers: bool | None = None) -> None:
        super().__init__(client)
        self._allow_barriers = (bool_env("P2P_POLICE_LLM_BARRIERS", False)
                                if allow_barriers is None else allow_barriers)

    def _decide_move(self, view: BrainView) -> Decision:
        # `_last_move` drives the backtrack tie-break and the no-second-STAY
        # rule, and the doctrine sets it to ITS choice on the way past - so the
        # value has to be corrected to whatever we actually play below.
        self.observe(view)
        fallback = super()._decide_move(view)
        if fallback.barrier is not None and not self._allow_barriers:
            self._settle(None)
            return fallback
        legal = view.board.legal_moves(view.own_pos)
        chosen = self.propose(self._prompt(view, legal), legal)
        self._settle(chosen)
        played = fallback.move if chosen is None else chosen
        self.played.append(played)
        if chosen is None:
            return fallback
        self._last_move = chosen
        return Decision(move=chosen)

    def _prompt(self, view: BrainView, legal: list[str]) -> str:
        return PROMPT.format(
            size=view.board.size, last=view.board.size - 1, own=list(view.own_pos),
            step=view.step, threshold=view.survival_threshold,
            remaining=view.steps_remaining,
            barriers=cells(sorted(view.board.barriers)) or "none",
            quota_left=max(0, view.barrier_quota - view.barriers_used),
            knowledge=knowledge(view),
            history=recent(self.played, self.trail, self.seen, self.walls),
            table=self._table(view, legal), moves=", ".join(legal))

    def _table(self, view: BrainView, legal: list[str]) -> str:
        """Each move's consequence, precomputed.

        An LLM is poor at breadth-first search over a walled grid and good at
        picking the smallest number in a list, so the search is done here and
        only the choice is left to it. Distances are BFS around barriers, not
        Manhattan - a wall between us makes the straight line a lie.
        """
        target = target_cell(view)
        rows = []
        for move in legal:
            landing = target_of(view.own_pos, move)
            reach = bfs_distances(view.board, landing)
            gap = reach.get(target) if target is not None else None
            note = "unknown - no fix on the thief yet" if gap is None else f"{gap} steps away"
            rows.append(f"  {move:<4} -> you stand on {list(landing)}, thief {note}")
        return "\n".join(rows)


def knowledge(view: BrainView) -> str:
    """What we legitimately know about the opponent, strongest evidence first.

    `opp_cells` is a *proof* - the cells it can be standing on, read off its own
    published field by inverting the negotiated physics - so it is stated before
    the belief map, which is an estimate. Handing a model both without saying
    which is which invites it to average them.
    """
    lines = []
    if view.opp_cells:
        lines.append(f"The opponent is provably on one of these cells: "
                     f"{cells(view.opp_cells)}.")
    if view.opp_lead is not None:
        lines.append(f"If it keeps running straight it reaches {list(view.opp_lead)} next.")
    if view.opp_cells:
        # The belief tail is suppressed once a proof exists. Printing a 2%
        # uniform smear beside a certainty is not extra evidence, it is an
        # invitation to average the two - and only one of them is ever exact.
        return "\n".join(lines)
    ranked = sorted(
        ((view.belief.grid[r][c], (r, c)) for r in range(view.board.size)
         for c in range(view.board.size)), reverse=True)[:4]
    if ranked and ranked[0][0] > 0:
        estimate = ", ".join(f"{list(cell)} {p:.0%}" for p, cell in ranked if p > 0)
        lines.append(f"Belief map estimate (a guess, not a proof): {estimate}.")
    return "\n".join(lines) or "You have no fix on the opponent yet."


def target_cell(view: BrainView):
    """The single cell to chase: the proof if we have one, else the belief peak."""
    if view.opp_lead is not None:
        return view.opp_lead
    if view.opp_cells:
        return view.opp_cells[0]
    best = max(((view.belief.grid[r][c], (r, c)) for r in range(view.board.size)
                for c in range(view.board.size)), default=(0.0, None))
    return best[1] if best[0] > 0 else None


def cells(group) -> str:
    return " ".join(str(list(cell)) for cell in group)
