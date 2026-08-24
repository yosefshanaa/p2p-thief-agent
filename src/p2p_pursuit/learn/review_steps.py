"""Per-log analysis: read one sealed sub-game and fold it into a `Review`.

Split out of :mod:`.review` (§3.2). This module owns the reading of a single
log - whose steps are ours, which scent physics it was played under, whether
the sub-game was cut short - and the accumulation into the shared model.
"""

from __future__ import annotations

from ..domain.board import Board
from ..domain.rules import POLICE
from ..domain.scent import BOOK_V1, MODELS, SUBTRACTIVE_V1
from ..domain.scent_locate import fix_lag, locate_emitter
from ..domain.scent_subtractive import CENTER_INTENSITY, DECAY_PER_STEP
from ..strategy.pathing import bfs_distances
from .clone_data import _steps
from .review_model import LAG, SIZE, Review


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


def _cut_of(steps: list[dict], model: str) -> bool:
    """Which side of the decay this sub-game cut its transmitted packet from.

    The companion to :func:`_model_of`, and needed for the same reason: the cut
    is a per-opponent negotiated term (najamjad take it early, s82kma9e late)
    and the sub-game log does not name it either. Rebuilding a series on the
    wrong cut puts every field one decay away from the one actually served -
    measured, all 126 of the najamjad counted fields failed to reconstruct and
    the inverter's accuracy over the whole archive fell from >99% to 96.5%.

    Read off the emitter's own cell rather than searched, because under the
    subtractive model that cell is exactly the emission ceiling before the decay
    and exactly one decay below it after: 0.9 early, 0.8 late, with no third
    value possible. Verified across the archive - 126/126 at 0.9 for najamjad,
    322/322 at 0.8 for s82kma9e and uoh-ay26.

    Only the subtractive model has two cuts; the multiplicative ones decay by a
    factor and the flag does not reach them, so they answer False.
    """
    if model != SUBTRACTIVE_V1:
        return False
    for step in steps:
        if step["scent"]:
            row, col = step["after"]
            return step["scent"][row][col] > CENTER_INTENSITY - DECAY_PER_STEP / 2
    return False


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
            # An ADDITIONAL view, never a subtraction: `death_cells` keeps
            # counting every death so `death_corner_share` goes on measuring
            # exactly what it measured when the corner pathology was found.
            # Splitting the cage deaths out of it moved a historical number,
            # which is the wrong way to make a stale threshold pass.
            if "enclos" in ((log.get("result") or {}).get("cause") or ""):
                into.enclosure_deaths += 1
                into.enclosure_death_cells[ours[-1]["after"]] += 1

    # Estimator quality, against our own published fields and our own truth.
    scented = [s for s in ours if s["scent"]]
    model = _model_of(scented)
    cut = _cut_of(scented, model)
    lag = fix_lag(model)
    for a, b in zip(scented, scented[1:], strict=False):
        truth = (b if lag == 0 else a)["after"]
        peak = max(((r, c) for r in range(SIZE) for c in range(SIZE)),
                   key=lambda cell: b["scent"][cell[0]][cell[1]])
        into.fixes += 1
        into.argmax_right += peak == truth
        into.early_cut_fixes += cut
        into.early_cut_argmax_right += cut and peak == truth
        found = locate_emitter(a["scent"], b["scent"], size=SIZE, model=model,
                               serve_before_decay=cut)
        into.inverse_right += found == truth
        into.inverse_wrong += found is not None and found != truth

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
