"""The archive-review data model: one folded report over every sealed log.

Split out of :mod:`.review` so each file stays inside the guidelines' 150-line
limit (§3.2 - split, never compress). Three concerns, three modules: the model
here, the per-log analysis in :mod:`.review_steps`, and the folding + rendering
in :mod:`.review`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..domain.rules import POLICE, THIEF

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
    #: Transitions where inverting named the WRONG cell, as opposed to declining
    #: to name one. The distinction is the whole value of the estimator: a wrong
    #: fix sends the police to the wrong square, a declined one falls back to the
    #: belief. Over the whole archive this is zero, and `inverse_right` falls
    #: short of `fixes` only by the silences.
    inverse_wrong: int = 0
    fixes: int = 0
    #: How many of `fixes` came from a series served on the EARLY cut. The
    #: archive is mixed physics, so any rate taken across the whole of it is an
    #: average over two different observation models - and `argmax_right` in
    #: particular is a property of the cut, not of the estimator: the early cut
    #: leaves the emission ceiling on the emitter's own cell, so the argmax is
    #: simply correct there. Split any such rate on this before reading it.
    early_cut_fixes: int = 0
    #: Of `argmax_right`, how many came from an early-cut series. Expect these to
    #: be ALL of them: the early cut serves the emission ceiling on the emitter's
    #: own cell, so there the argmax is not an estimate at all, it is the answer.
    early_cut_argmax_right: int = 0
    #: Thief deaths by barrier cage rather than by pursuit - sealed with no open
    #: neighbour (book rule 47). A SUBSET of `death_cells`, not a partition of
    #: it, because `death_corner_share` is a historical measurement and moving
    #: its denominator would rewrite the finding it recorded.
    #:
    #: Worth its own counter because it is evidence about a *pursuer's barrier
    #: plan* rather than about where our estimator pointed us, and because it is
    #: the failure that is currently costing us: 9 of our 19 archived thief
    #: deaths, including all three windows of the counted najamjad series, where
    #: the cage closed on open ground at (2,4) five moves inside the survival
    #: threshold.
    enclosure_deaths: int = 0
    enclosure_death_cells: Counter = field(default_factory=Counter)
    death_cells: Counter = field(default_factory=Counter)
    per_match: dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        skip = ("death_cells", "enclosure_death_cells")
        payload = {k: v for k, v in vars(self).items() if k not in skip}
        payload["death_cells"] = [[list(c), n] for c, n in self.death_cells.most_common()]
        payload["enclosure_death_cells"] = [
            [list(c), n] for c, n in self.enclosure_death_cells.most_common()]
        return payload
