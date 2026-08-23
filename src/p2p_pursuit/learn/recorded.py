"""Sparring partners that replay what a team actually did, state by state.

The pool already had two ways to model a played opponent and both answer the
wrong question for most teams:

* :class:`~.clone_fit.ClonedBrain` fits a small linear policy. It generalises,
  but it reproduces only about three moves in four, and the quarter it gets
  wrong is not noise - it is the part of the opponent that is *distinctive*.
* :class:`~.opponents.Scripted` replays a fixed move sequence. Exact, but only
  honest for a deterministic opponent, and of the eight teams in ``matches/``
  only gal-roy1's thief and s82kma9e's police actually are one. Everybody else
  reacts to where we stand, so a fixed script models a different opponent every
  time our own doctrine changes - which is precisely when we are searching.

This is the third option and the one that fits a *reactive* opponent: keep every
observed decision, and when asked to move, play the move they played from the
nearest state we ever saw them in. No model, no fit, nothing to over-generalise;
where the state was actually observed the reproduction is exact, and where it
was not the answer degrades toward the nearest thing they really did rather than
toward a line drawn through their behaviour.

Distance weights their own cell above ours, because a team's policy is mostly a
function of where *it* is, and ties break toward the move they played most
often, which keeps the partner deterministic across a whole search.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..domain.board import Cell
from ..domain.brains_base import BrainBase, BrainView
from ..domain.rules import Decision
from .clone_data import Sample

#: Our cell matters, but theirs matters more: an evader's next move is mostly a
#: function of the ground it is standing on, and only then of the threat.
OWN_WEIGHT = 3
FAR = 999


class Recorded(BrainBase):
    """Replays the move a team played from the nearest state we ever saw."""

    def __init__(self, rows: list[dict]) -> None:
        if not rows:
            raise ValueError("a recorded opponent needs at least one observed decision")
        self.rows = rows

    def nearest(self, own: Cell, pursuer: Cell, prev: str | None) -> dict | None:
        """The decision they took from the observed state nearest to this one."""
        best, best_key = None, None
        for row in self.rows:
            pos, opp = row["pos"], row["pursuer"]
            key = (OWN_WEIGHT * (abs(pos[0] - own[0]) + abs(pos[1] - own[1]))
                   + abs(opp[0] - pursuer[0]) + abs(opp[1] - pursuer[1])
                   + (0 if row["prev_move"] == prev else 1),
                   -row["weight"])
            if best_key is None or key < best_key:
                best, best_key = row, key
        return best

    def move_for(self, own: Cell, pursuer: Cell, prev: str | None) -> str:
        """The move they played from the nearest observed state.

        Public because it is also how the table is *scored*: `agreement` replays
        held-out decisions through exactly the lookup a game would use, rather
        than through a second implementation of it.
        """
        row = self.nearest(own, pursuer, prev)
        return (row["move"] if row else None) or "STAY"

    def _threat(self, view: BrainView) -> Cell:
        # The table was built against our *true* cell, so the lookup wants the
        # closest thing this view has to one: the scent fix, and the belief peak
        # only when there is no fix.
        return view.opp_fix or view.belief.argmax()

    def _pick_move(self, view: BrainView) -> Decision:
        move = self.move_for(view.own_pos, self._threat(view), getattr(self, "_last", None))
        legal = view.board.legal_moves(view.own_pos)
        if move not in legal:
            move = "STAY" if "STAY" in legal else legal[0]
        self._last = move
        return Decision(move=move)

    def _decide_move(self, view: BrainView) -> Decision:
        """As police, replay the *whole* decision - the wall included.

        Stored as an offset from their own cell rather than an absolute one,
        because a barrier is only legal beside the police and the useful thing
        to reproduce is the geometry of the placement, not the coordinate. That
        also lets one observed decision answer a state a few cells away, which
        is the whole point of a nearest-state table.
        """
        row = self.nearest(view.own_pos, self._threat(view), getattr(self, "_last", None))
        offset = row.get("barrier") if row else None
        if offset is not None and view.barriers_used < view.barrier_quota:
            cell = (view.own_pos[0] + offset[0], view.own_pos[1] + offset[1])
            if view.board.is_open(cell) and cell != view.own_pos:
                self._last = "STAY"
                return Decision(move="STAY", barrier=cell)
        return self._pick_move(view)


def table_from_samples(samples: list[Sample]) -> dict[str, list[dict]]:
    """Collapse observed decisions into one deduplicated table per role.

    Identical states seen more than once collapse to a single row carrying the
    count, so the tie-break can prefer the move a team played most often from
    ground it visited repeatedly - and so a match replayed six times does not
    outvote a match played once.
    """
    counted: dict[tuple, Counter] = {}
    for s in samples:
        key = (s.role, s.pos, s.pursuer, s.prev_move)
        # The decision is the move *and* the wall: collapsing on the move alone
        # would let three plain STAYs outvote the one turn they spent building.
        offset = None if s.barrier is None else (s.barrier[0] - s.pos[0],
                                                 s.barrier[1] - s.pos[1])
        counted.setdefault(key, Counter())[(s.move, offset)] += 1
    out: dict[str, list[dict]] = {}
    for (role, pos, pursuer, prev), decisions in counted.items():
        (move, offset), weight = decisions.most_common(1)[0]
        out.setdefault(role, []).append(
            {"pos": list(pos), "pursuer": list(pursuer), "prev_move": prev,
             "move": move, "barrier": list(offset) if offset else None,
             "weight": weight})
    return out


def agreement(rows: list[dict], samples: list[Sample]) -> float:
    """Share of held-out decisions this table reproduces."""
    if not samples:
        return 0.0
    brain = Recorded(_hydrate(rows))
    hit = sum(brain.move_for(s.pos, s.pursuer, s.prev_move) == s.move for s in samples)
    return hit / len(samples)


def _hydrate(rows: list[dict]) -> list[dict]:
    return [{"pos": tuple(r["pos"]), "pursuer": tuple(r["pursuer"]),
             "prev_move": r["prev_move"], "move": r["move"],
             "barrier": tuple(r["barrier"]) if r.get("barrier") else None,
             "weight": int(r.get("weight", 1))} for r in rows]


def load_tables(directory: Path) -> dict[str, dict[str, list[dict]]]:
    """Every recorded team in ``<directory>/recorded``, keyed by team then role."""
    found: dict[str, dict[str, list[dict]]] = {}
    for path in sorted((directory / "recorded").glob("*.json")):
        roles = json.loads(path.read_text(encoding="utf-8")).get("roles", {})
        table = {role: _hydrate(rows) for role, rows in roles.items() if rows}
        if table:
            found[path.stem] = table
    return found
