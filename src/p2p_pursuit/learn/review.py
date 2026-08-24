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

Those are the counts of what was *played*, and they stay that way: this module
reads the archive, it does not re-decide it. What the current brain would do
from the same 76 states is a different question and a strictly harder one - the
opponent's served field is not archived, though it rebuilds exactly from the
trajectory that is. :mod:`.counterfactual` answers it, and its answer - 26
converted, with the barrier and stand-still misses both at zero - is pinned in
``tests/unit/test_archive_review`` rather than reported here.

**Was the position estimate any good?** Both brains read the opponent's cell off
``argmax`` of its served scent field. Replaying that against the truth in the
same records: right 11% of the time, because the field saturates and most served
fields have 6 to 20 cells tied at the maximum. Inverting the field instead
(:mod:`...domain.scent_locate`) is exact.

**Where did the thief die?** Not evenly: 11 of 19 captures are on the bottom and
right edges, and the thief finished its move inside the pursuer's next-step
reach on 45 turns to get there.

And increasingly, not by pursuit at all. **9 of those 19 are enclosures** - a
barrier cage sealed around a thief that never saw it being built - including all
three thief windows of the counted najamjad series, where the box shut on open
ground at (2,4) five moves inside the survival threshold. That is the failure
currently costing us 20 points a window, and it is counted separately
(`enclosure_deaths`) precisely because it says nothing about the estimator.

The numbers printed here are the ones quoted in the brains' own docstrings and
in ``docs/STRATEGY.md``; running this is how they stay honest.
"""

from __future__ import annotations

import json
from pathlib import Path

from .review_model import LAG, SIZE, Review
from .review_steps import _cut_of, _model_of, _our_steps, review_log

__all__ = ["LAG", "SIZE", "Review", "_cut_of", "_model_of", "_our_steps",
           "death_corner_share", "format_review", "review", "review_log"]


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
