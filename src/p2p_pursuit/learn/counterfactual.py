"""Replay the archive's police turns through a doctrine that did not play them.

:mod:`.review` counts what we *did*. It cannot say whether a change helped,
because every log in ``matches/`` was played by the doctrine of its day - so the
famous "76 chances, 11 taken" is a fact about a brain that no longer exists, and
quoting it as a live defect is how a fixed bug gets fixed twice.

This asks the counterfactual instead: standing in exactly the state the archive
records, what does *this* doctrine do? Two things make that honest, and one
makes it partial.

**The opponent's field is not archived - but it is recoverable.** A step record
carries our own served field and their position, never their field. A served
field is a pure function of the trajectory that emitted it, though, so it can be
rebuilt: :func:`served_fields` replays their cells through
:class:`~..domain.scent.ScentField`. Checked against the fields the archive
*does* store - our own - the reconstruction is bit-identical on all 2429 of them,
across all three negotiated physics, so the tracker sees what it would have seen.

**The state is fixed, the decision is not.** Positions come from the archive, so
this measures one turn at a time and never compounds: it answers "was this turn
converted", not "would the sub-game have been won". That is the question the
conversion statistic asks anyway, and it is the reason the answer is trustworthy
where a full re-simulation against a frozen opponent would not be.

**The belief is a stub, and belief-gated branches cannot be judged here.** A
:class:`~..domain.belief.BeliefMap` is built from hints, claims and the opponent's
public records, which no single log carries enough of to rebuild. The pounce and
the pursuit's capture term read the scent tracker rather than the belief, which
is why they can be measured this way; ``_barrier_play``'s kill shot and corner
seal cannot, and a result about them from this module means nothing.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from ..domain.belief import BeliefMap
from ..domain.board import Board, Cell, target_of
from ..domain.brains_base import BrainView
from ..domain.rules import POLICE
from ..domain.scent import ScentField
from ..domain.tracking import OpponentTracker
from ..strategy.params import Doctrine
from ..strategy.police_brain import PoliceBrain
from .clone_data import _steps
from .review import LAG, SIZE, _cut_of, _model_of, _our_steps

Field = list[list[float]]
#: The archive's own shared config: 14 barriers, 40 moves, survival at 35.
QUOTA, MOVES, SURVIVAL = 14, 40, 35


@dataclass
class Conversion:
    """The same four buckets :class:`~.review.Review` counts, re-decided."""

    chances: int = 0
    converted: int = 0
    barred_the_thief: int = 0
    lost_to_barrier: int = 0
    lost_standing_still: int = 0
    lost_walking_elsewhere: int = 0

    @property
    def rate(self) -> float:
        return self.converted / max(self.chances, 1)


def served_fields(cells: dict[int, Cell], model: str, size: int = SIZE,
                  serve_before_decay: bool = False) -> dict[int, Field]:
    """The field an agent served at each of its steps, from its trajectory alone.

    The emitter's own history is the only input a scent model has, so replaying
    the cells in step order reproduces the served field exactly - which is what
    makes an opponent whose fields were never archived trackable anyway.

    ``serve_before_decay`` has to match the match being replayed: reconstructing
    a najamjad series on the default cut hands the brain fields 0.1 below the
    ones it actually saw, and a counterfactual asked on the wrong observation
    answers a question nobody asked.
    """
    field = ScentField(size=size, model=model, serve_before_decay=serve_before_decay)
    return {step: field.serve_for_step(cells[step]) for step in sorted(cells)}


def _view(step: dict, board: Board, tracker: OpponentTracker, served: Field | None,
          sub_game: int, barriers_used: int) -> BrainView:
    blank = [[0.0] * SIZE for _ in range(SIZE)]
    return BrainView(
        role=POLICE, sub_game=sub_game, step=step["step"], own_pos=step["before"],
        board=board, belief=BeliefMap(SIZE),          # a stub - see the module docstring
        opp_scent=served or blank, own_scent=step["scent"] or blank,
        barriers_used=barriers_used, barrier_quota=QUOTA,
        steps_remaining=max(1, MOVES - step["step"]), survival_threshold=SURVIVAL,
        trust=1.0, map_area="urban", rng=random.Random(step["step"]),
        opp_cells=tuple(tracker.possible(board)), opp_fix=tracker.fix,
        opp_fix_lag=tracker.lag, opp_lead=tracker.projected(board), claim_enclosure=True)


def replay_log(log: dict, doctrine: Doctrine, into: Conversion) -> None:
    """Re-decide one sealed police sub-game, folding it into the running totals."""
    if (log.get("perspective") or POLICE) != POLICE:
        return
    ours = _our_steps(log)
    theirs = {s["step"]: tuple(s["pos"]) for s in _steps(log.get("opponent_records", []))}
    scented = [s for s in ours if s["scent"]]
    if not ours or not theirs or len(scented) < 3:
        return
    model = _model_of(scented)
    # Both halves of the physics, inferred from our own archived fields. The cut
    # is a per-opponent term and the log does not name it, so a series played on
    # the early cut rebuilds one decay low on every field unless it is detected -
    # and a counterfactual asked on the wrong observation answers nothing.
    cut = _cut_of(scented, model)
    served = served_fields(theirs, model, serve_before_decay=cut)
    brain = PoliceBrain(doctrine)
    tracker = OpponentTracker(SIZE, model, serve_before_decay=cut)
    board, used = Board(SIZE), 0
    for step in ours:
        if step["barrier"]:
            board.add_barrier(step["barrier"])
            used += 1
        them = theirs.get(step["step"] - LAG[POLICE])
        if them is None:
            continue
        if step["step"] in served:
            tracker.observe(served[step["step"]], board)
        # Decided on EVERY turn, including the ones that are not chances: the
        # brain carries rolling state - the peak window, the gap window, the
        # last move - so skipping ahead to the interesting turns would ask it
        # what it thinks having shown it none of the game.
        decision = brain._decide_move(
            _view(step, board, tracker, served.get(step["step"]), log.get("sub_game", 1), used))
        if them not in {step["before"], *board.open_neighbors(step["before"])}:
            continue
        into.chances += 1
        landed = step["before"] if decision.barrier else target_of(step["before"], decision.move)
        if decision.barrier is not None and tuple(decision.barrier) == them:
            into.barred_the_thief += 1
        elif landed == them:
            into.converted += 1
        elif decision.barrier is not None:
            into.lost_to_barrier += 1
        elif landed == step["before"]:
            into.lost_standing_still += 1
        else:
            into.lost_walking_elsewhere += 1


def replay(doctrine: Doctrine, root: Path = Path("matches")) -> Conversion:
    """Every sealed police sub-game under ``root``, re-decided by ``doctrine``.

    Strictly read-only over the archive, for the same reason :mod:`.review` is:
    those logs are the audit trail of counted matches.
    """
    out = Conversion()
    for path in sorted(root.rglob("log_*.json")):
        log = json.loads(path.read_text(encoding="utf-8"))
        if log.get("report_type") == "sub_game_log":
            replay_log(log, doctrine, out)
    return out
