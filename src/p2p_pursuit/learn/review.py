"""Read the played archive back as evidence: what did we actually do wrong?

Every sealed sub-game log carries both trajectories - ours in ``my_records``
with explicit ``pos_before``/``pos_after``, theirs in ``opponent_records``
under whichever of four spellings their dialect uses. That is not just a result;
it is a few thousand turns of ground truth against which a doctrine's claims can
be checked rather than asserted.

This module is strictly read-only over ``matches/``. It answers three questions,
each of which turned out to have an uncomfortable answer:

**Did the police convert?** A capture needs our cell to *become* the thief's
cell, so a turn where the thief stands one step away is a chance. Counting them
across the archive: 76 chances, 11 taken. Twenty-seven of the misses were spent
placing a barrier - which forfeits the move - from a cell adjacent to the thief.

**Was the position estimate any good?** Both brains read the opponent's cell off
``argmax`` of its served scent field. Replaying that against the truth in the
same records: right 11% of the time, because the field saturates and most served
fields have 6 to 20 cells tied at the maximum. Inverting the field instead
(:mod:`...domain.scent_locate`) is exact.

**Where did the thief die?** Not evenly: 11 of 14 captures are on the bottom and
right edges, and the thief finished its move inside the pursuer's next-step
reach on 43 turns to get there.

The numbers printed here are the ones quoted in the brains' own docstrings and
in ``docs/STRATEGY.md``; running this is how they stay honest.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..domain.board import Board
from ..domain.rules import POLICE, THIEF
from ..domain.scent import BOOK_V1, MODELS
from ..domain.scent_locate import fix_lag, locate_emitter
from ..strategy.pathing import bfs_distances
from .clone_data import _steps

SIZE = 7
#: The thief moves first in every config we have played (`first_mover: thief`),
#: so a police deciding at step k faces a thief that has already moved this
#: round, and a thief deciding at step k faces a pursuer that has not. Getting
#: this backwards makes every conversion statistic below off by one turn.
LAG = {POLICE: 0, THIEF: 1}


@dataclass
class Review:
    """What the archive says, in the terms the doctrine is written in."""

    sub_games: int = 0
    police_sub_games: int = 0
    thief_sub_games: int = 0
    captures_for: int = 0
    captures_against: int = 0
    chances: int = 0
    converted: int = 0
    lost_to_barrier: int = 0
    lost_standing_still: int = 0
    lost_walking_elsewhere: int = 0
    exposures: int = 0
    cut_off_turns: int = 0
    barriers_placed: int = 0
    argmax_right: int = 0
    inverse_right: int = 0
    fixes: int = 0
    death_cells: Counter = field(default_factory=Counter)
    per_match: dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        payload = {k: v for k, v in vars(self).items() if k not in ("death_cells",)}
        payload["death_cells"] = [[list(c), n] for c, n in self.death_cells.most_common()]
        return payload


def _our_steps(log: dict) -> list[dict]:
    return sorted(({"step": int(r["step"]), "before": tuple(r["pos_before"]),
                    "after": tuple(r["pos_after"]), "move": r.get("move"),
                    "scent": r.get("scent"),
                    "barrier": tuple(r["barrier"]) if r.get("barrier") else None}
                   for r in log.get("my_records", []) if r.get("kind") == "step"),
                  key=lambda s: s["step"])


def _model_of(steps: list[dict]) -> str:
    """Which physics this sub-game served under, inferred from its own fields.

    Not read from the config: the archive spans three negotiated models and the
    sub-game logs do not name theirs, but each model has a distinct ceiling and,
    more reliably, only the right one inverts its own transitions.
    """
    best, best_hits = BOOK_V1, -1
    for model in MODELS:
        lag = fix_lag(model)
        hits = sum(locate_emitter(a["scent"], b["scent"], size=SIZE, model=model)
                   == (b if lag == 0 else a)["after"]
                   for a, b in zip(steps, steps[1:], strict=False)
                   if a["scent"] and b["scent"])
        if hits > best_hits:
            best, best_hits = model, hits
    return best


def review_log(log: dict, into: Review) -> None:
    """Fold one sealed sub-game into the running totals."""
    role = log.get("perspective") or POLICE
    ours = _our_steps(log)
    theirs = {s["step"]: s["pos"] for s in _steps(log.get("opponent_records", []))}
    if not ours or not theirs:
        return
    into.sub_games += 1
    ending = (log.get("result") or {}).get("ending")
    if role == POLICE:
        into.police_sub_games += 1
        into.captures_for += ending == "capture"
    else:
        into.thief_sub_games += 1
        into.captures_against += ending == "capture"
        if ending == "capture":
            into.death_cells[ours[-1]["after"]] += 1

    # Estimator quality, against our own published fields and our own truth.
    scented = [s for s in ours if s["scent"]]
    model = _model_of(scented)
    lag = fix_lag(model)
    for a, b in zip(scented, scented[1:], strict=False):
        truth = (b if lag == 0 else a)["after"]
        peak = max(((r, c) for r in range(SIZE) for c in range(SIZE)),
                   key=lambda cell: b["scent"][cell[0]][cell[1]])
        into.fixes += 1
        into.argmax_right += peak == truth
        into.inverse_right += locate_emitter(
            a["scent"], b["scent"], size=SIZE, model=model) == truth

    board = Board(SIZE)
    far = SIZE * SIZE
    for step in ours:
        if step["barrier"]:
            board.add_barrier(step["barrier"])
            into.barriers_placed += 1
        them = theirs.get(step["step"] - LAG[role])
        if them is None:
            continue
        if role == POLICE:
            if them in {step["before"], *board.open_neighbors(step["before"])}:
                into.chances += 1
                if step["after"] == them:
                    into.converted += 1
                elif step["barrier"]:
                    into.lost_to_barrier += 1
                elif step["after"] == step["before"]:
                    into.lost_standing_still += 1
                else:
                    into.lost_walking_elsewhere += 1
            if bfs_distances(board, step["after"]).get(them, far) >= far:
                into.cut_off_turns += 1
        elif step["after"] in {them, *board.open_neighbors(them)}:
            into.exposures += 1


def review(root: Path = Path("matches")) -> Review:
    """Every sealed sub-game under ``root``, folded into one report."""
    out = Review()
    for path in sorted(root.rglob("log_*.json")):
        log = json.loads(path.read_text(encoding="utf-8"))
        if log.get("report_type") != "sub_game_log":
            continue
        before = out.sub_games
        review_log(log, out)
        if out.sub_games > before:
            out.per_match.setdefault(path.parent.parent.name, {"sub_games": 0})
            out.per_match[path.parent.parent.name]["sub_games"] += 1
    return out


def format_review(r: Review) -> str:
    """The report, in the words the doctrine's own comments use."""
    lines = [
        f"{r.sub_games} sealed sub-games ({r.police_sub_games} as police, "
        f"{r.thief_sub_games} as thief) across {len(r.per_match)} match directories",
        "",
        "POLICE - conversion (a chance is a turn that began with the thief one step away)",
        f"  {r.chances:5d}  chances",
        f"  {r.converted:5d}  converted    ({r.converted / max(r.chances, 1):.0%})",
        f"  {r.lost_to_barrier:5d}  spent the turn placing a barrier instead",
        f"  {r.lost_standing_still:5d}  stood still",
        f"  {r.lost_walking_elsewhere:5d}  walked somewhere else",
        f"  {r.captures_for:5d}  sub-games actually won by capture",
        f"  {r.barriers_placed:5d}  barriers placed, "
        f"{r.cut_off_turns} turns left unable to reach the thief at all",
        "",
        "THIEF - exposure (a turn our move ENDED inside the pursuer's next-step reach)",
        f"  {r.exposures:5d}  exposures",
        f"  {r.captures_against:5d}  captures against us",
        "  death cells: " + ", ".join(f"{tuple(c)}x{n}" for c, n in r.death_cells.most_common(6)),
        "",
        "POSITION ESTIMATE - our own served fields against our own recorded cells",
        f"  {r.argmax_right:5d} / {r.fixes}  ({r.argmax_right / max(r.fixes, 1):.0%})  "
        f"argmax of the served field - the estimator both brains used to v5",
        f"  {r.inverse_right:5d} / {r.fixes}  ({r.inverse_right / max(r.fixes, 1):.0%})  "
        f"inverting the model - what they use now",
    ]
    return "\n".join(lines)


def death_corner_share(r: Review) -> float:
    """Share of our thief's deaths on the bottom or right edge.

    The tell that the old estimator was not merely noisy but *biased*: ``max``
    returns the first of the tied maximal cells in row-major order, which points
    at the top-left, and a thief weighting that at `w_trail` runs away from it.
    """
    total = sum(r.death_cells.values())
    edge = sum(n for (row, col), n in r.death_cells.items()
               if row == SIZE - 1 or col == SIZE - 1)
    return edge / max(total, 1)
