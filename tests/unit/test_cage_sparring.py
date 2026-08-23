"""The opponent the thief objective could not see, and the two ways it was faked.

`evader` was added because every sparring thief read the belief rather than
inverting the field, so the police search met nobody who could hold a gap and
duly certified a doctrine that converted 0 of 6 on the wire. The thief half of
the pool has the mirror-image hole, and the archive names it: of the eight
counted sub-games in which our thief was captured, four say ``barrier onto ...``
or ``enclosed``, and all eight end on the outer ring or one step off it.

`Cager` is meant to be that opponent. It was added in this state and shipped
twice before it ever placed a barrier, and this file exists mostly to pin down
the two reasons, because both produced *numbers that read as policy results*:

* **It could not seal.** It scored a candidate barrier by the Voronoi room it
  took off the thief. The rules let a police wall its own cell or an orthogonal
  neighbour, and a cell next to the police is a cell the police reaches first,
  so such a cell is never in the thief's room: the best available gain measured
  exactly 0 on all 1825 in-range turns of a 40-seed sequence. No `seal_gain`
  could have fired it. It now scores the ground a barrier takes off the thief -
  cells it can still reach - which is the measure a cage can be *built* along,
  because the early barriers of a cage buy no room at all.
* **The second ordering did not play.** A variant ranked room ahead of gap when
  choosing a move, and our thief lost to it 40 in 40 while `evader` survived it
  40 in 40 - which was read as the live loss reproduced and a reachable policy
  gap. It was neither. That police made 0 moves in 1360 turns against `evader`
  and visited one cell; our thief simply walked itself into a corner and then
  into a stationary pursuer. The room metric hardly responds to a police step at
  any distance, so leading with it is a rule that prefers standing still, and
  gating it to close range still left it moving on 6% of turns. It is gone.

What remains is a cage that cages: it spends barriers, and both our thief and
`evader` survive it. That is a fair state for the pool to be in - the sparring
police that beats our thief is our own, through `mirror` - and it is an honest
one, which the 0-of-40 it replaced was not.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.domain.scent import SUBTRACTIVE_V1
from p2p_pursuit.domain.scoring import CAPTURE, SURVIVAL
from p2p_pursuit.learn import arena
from p2p_pursuit.learn.arena import default_shared, sub_game
from p2p_pursuit.learn.opponents import Cager
from p2p_pursuit.learn.population import BUILTIN, build
from p2p_pursuit.learn.population import ours as ours_brain
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from p2p_pursuit.strategy.params import active
from p2p_pursuit.strategy.thief_brain import ThiefBrain

#: The physics the two teams that beat our thief actually served, and the
#: doctrine we played against them. Both are named rather than inherited: the
#: effect is a lag-0 model handing the pursuer an exact fix, and it is invisible
#: under book_v1, where the same fix arrives a step stale.
DOCTRINE = Path("config/doctrine-subtractive.json")
SEEDS = tuple(range(4000, 4040))


@pytest.fixture
def subtractive(monkeypatch):
    monkeypatch.setattr(arena, "QUIET",
                        dataclasses.replace(arena.QUIET, scent_model=SUBTRACTIVE_V1))
    return active(DOCTRINE)


def _play(thief, police, seeds=SEEDS):
    """Every sub-game of the sequence, as (endings, police decisions).

    ``police`` is a factory rather than a pool name so that `mirror` can be
    built against the doctrine under test. `population.ours` with no doctrine
    reads `P2P_DOCTRINE`, which pytest does not set, so naming the member here
    would quietly measure our BOOK police against subtractive physics - which
    is a different pursuer, and one this thief happens to survive 40 in 40.
    """
    out = []
    seen: list[tuple] = []
    original = Cager._decide_move

    def watched(self, view):
        decision = original(self, view)
        seen.append((view.own_pos, decision.move, decision.barrier))
        return decision

    Cager._decide_move = watched
    try:
        for index, seed in enumerate(seeds):
            ending, _, _ = sub_game(default_shared(), police(), thief(),
                                    seed, always_claim=bool(index % 2))
            out.append(ending)
    finally:
        Cager._decide_move = original
    return out, seen


def _survival(thief, police) -> float:
    endings, _ = _play(thief, police)
    return sum(e != CAPTURE for e in endings) / len(endings)


def _series_survival(thief, police, windows: int = 6, seeds=SEEDS[:20]) -> float:
    """Survival across a whole match, with both brains kept between windows.

    `_play` builds a fresh pair for every seed, so anything either side
    remembers *between* sub-games is invisible to it. That was fine while no
    brain remembered anything; `w_grave` made it wrong.
    """
    good = played = 0
    for index, seed in enumerate(seeds):
        peer = dataclasses.replace(arena.QUIET, always_claim=bool(index % 2))
        cop = TurnEngine(POLICE, default_shared(), peer, brain=police(), seed=seed * 2)
        robber = TurnEngine(THIEF, default_shared(), peer, brain=thief(), seed=seed * 2 + 1)
        for window in range(1, windows + 1):
            cop.start_sub_game(window)
            robber.start_sub_game(window)
            play_sub_game(cop, robber)
            good += (robber.end.ending if robber.end else SURVIVAL) != CAPTURE
            played += 1
    return good / played


def _cager():
    return BUILTIN["cager"].make(POLICE)


def _evader():
    return BUILTIN["evader"].make(THIEF)


def test_the_cage_actually_spends_barriers(subtractive):
    """The whole point of the archetype, and for two commits it did none of it.

    Asserted as a rate rather than a bare "at least one": the failure mode was
    total, so a single lucky placement would not distinguish a cage from the
    chaser this brain silently was.
    """
    _, seen = _play(lambda: ThiefBrain(subtractive), _cager, SEEDS[:8])
    barriers = [cell for _, _, cell in seen if cell is not None]
    assert len(barriers) >= 8, (
        f"{len(barriers)} barriers across 8 sub-games - the cage is not caging")
    assert not [own for own, _, cell in seen if cell == own], (
        "a barrier on our own cell forfeits the move and walls nothing")


def test_the_cage_is_a_pursuer_and_not_a_statue(subtractive):
    """What the removed ordering failed, silently, while scoring 40-0.

    A police that never moves still produces a survival rate, and that rate
    looks exactly like a policy result until somebody counts the moves.
    """
    _, seen = _play(lambda: ThiefBrain(subtractive), _cager, SEEDS[:8])
    moved = sum(1 for _, move, cell in seen if move != "STAY" and cell is None)
    assert moved > len(seen) // 2, f"the cage moved on {moved}/{len(seen)} turns"
    assert len({own for own, _, _ in seen}) > 4, "the cage barely left its start cell"


def test_our_thief_survives_the_cage_that_cages(subtractive):
    """The claim the removed archetype was making, tested against a real one.

    Our thief was said to have no answer to being herded. Against the cage now
    that it builds cages, it survives every seed - as does `evader`, so this is
    not an opponent too weak to separate the two.
    """
    assert _survival(lambda: ThiefBrain(subtractive), _cager) == 1.0
    assert _survival(_evader, _cager) == 1.0


def test_the_sparring_police_that_does_beat_our_thief_is_our_own(subtractive):
    """Where the thief objective's remaining signal comes from.

    With the fake removed, `mirror` is the member that separates evaders: it
    takes `evader` on a quarter of the seeds. The assertion is deliberately one
    of *separation* rather than a pinned rate - the point is that the pool still
    contains something a thief search can lose to.

    Scored over a SIX-WINDOW SERIES rather than over forty first meetings, and
    that is not a convenience - it is the only form in which the comparison
    means anything. Our thief carries `w_grave`, which by construction cannot
    help in the first window of a match: it prices the cell a *previous* window
    died on. Measured 2026-08-23 under the counted physics, alternating the
    claim regime exactly as `_play` does:

        one sub-game    ours 0.500   evader 0.625
        six windows     ours 0.725   evader 0.717

    So over a single first meeting the naive archetype is genuinely ahead - our
    thief pays for its other terms in window one - and over a match it is not.
    A match is six windows, so six windows is the honest denominator.
    """
    police = lambda: ours_brain(POLICE, subtractive)  # noqa: E731
    ours = _series_survival(lambda: ThiefBrain(subtractive), police)
    theirs = _series_survival(_evader, police)
    assert theirs < 1.0, "mirror catches nobody - the thief objective is blind again"
    assert ours >= theirs, (
        f"our tuned thief survives a series against our own police {ours:.3f} of "
        f"the time and the naive `evader` archetype manages {theirs:.3f} - the "
        f"doctrine is losing to the archetype it was built to beat")


def test_the_cage_is_registered_for_the_police_seat_only():
    """A thief cannot place a barrier, so a cage in the thief seat is a no-op."""
    assert build(("cager",))["cager"].roles == (POLICE,)
