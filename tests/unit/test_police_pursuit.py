"""The pursuit term's units, and the live position that exposed them.

Every counted match we lost was lost by the police, and the police was lost by
an arithmetic mistake rather than a strategic one. `_pursue` scores a candidate
cell as ``d - w_cut * cut``: `d` is the distance to the quarry, 0..12 on this
board, and `cut` was a raw count of the cells we reach no later than the thief,
0..49. At the searched weight of 0.96 that made a cell of territory worth
twelve steps of pursuit, and the cell owning the most territory is the middle
of the board - so the police stood in the middle of the board.

It is not an inference. Replaying the sealed archive of the C001 series against
uoh-ay26 through the raw term reproduces the police's actual play exactly: it
predicts STAY on 54 of 102 turns, and the police played STAY on 54 of 102
turns, 48 of them with no barrier to show for it. Normalised, the same term
predicts STAY on none of them and closes the gap on all 102.

These tests pin the units, the live position, and the pool member that can tell
the difference - because the search cannot. Against every sparring partner that
existed before `evader`, camping in the middle converts 100%, which is why the
search chose it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from p2p_pursuit.domain.board import Board, target_of
from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.domain.scent import SUBTRACTIVE_V1
from p2p_pursuit.domain.scoring import CAPTURE
from p2p_pursuit.learn import arena
from p2p_pursuit.learn.arena import default_shared, sub_game
from p2p_pursuit.learn.opponents import Evader
from p2p_pursuit.learn.population import BUILTIN, ours
from p2p_pursuit.strategy.params import active
from p2p_pursuit.strategy.pathing import bfs_distances

SIZE = 7
AREA = SIZE * SIZE
#: The pairing the counted match was played on. Named here rather than inherited
#: from the ambient environment, because the effect being measured lives in this
#: doctrine's `w_cut` (0.96) and is nearly invisible in the book's (0.13) - which
#: is also why gal-roy1 shows 0 camping turns and uoh-ay26 shows 48.
DOCTRINE = Path("config/doctrine-subtractive.json")


@pytest.fixture
def played(monkeypatch):
    """Run the arena on the physics and doctrine the C001 series actually used."""
    monkeypatch.setattr(arena, "QUIET",
                        dataclasses.replace(arena.QUIET, scent_model=SUBTRACTIVE_V1))
    return active(DOCTRINE)
#: police cell, thief cell - lifted from log_AHK-YOSI-vs-uoh-ay26-C001_g01.json,
#: our step 10. The board still had no barriers on it at that point.
LIVE = ((3, 3), (2, 4))


def _score(board: Board, own, quarry, move: str, w_cut: float, *, normalised: bool):
    """`_pursue`'s objective for one candidate move, both ways of counting."""
    to_quarry = bfs_distances(board, quarry)
    pos = target_of(own, move)
    from_pos = bfs_distances(board, pos)
    cut = sum(1 for cell, theirs in to_quarry.items()
              if from_pos.get(cell, AREA) <= theirs)
    return to_quarry.get(pos, 9999) - w_cut * (cut / AREA if normalised else cut)


@pytest.mark.parametrize("w_cut", [0.0, 0.13317, 0.5, 0.959542, 1.0])
def test_a_step_of_pursuit_outweighs_every_cell_of_territory(w_cut: float):
    """The units, stated as the property that was violated.

    Territory is a tie-break between equally close cells, so the most it may
    ever be worth is less than the one point that separates a closer cell from
    a further one. Counted raw it was worth 11.5, and the police stood still.

    Asserted over the whole board rather than at one position: the swing is
    ``w_cut * (max_cut - min_cut) / AREA``, and the widest swing any position
    can produce is the full board, so this holds everywhere for w_cut <= 1.
    """
    board = Board(SIZE)
    quarry = LIVE[1]
    worst = 0.0
    for row in range(SIZE):
        for col in range(SIZE):
            own = (row, col)
            if own == quarry:
                continue
            scores = [_score(board, own, quarry, m, w_cut, normalised=True)
                      - bfs_distances(board, quarry).get(target_of(own, m), 9999)
                      for m in board.legal_moves(own)]
            worst = max(worst, max(scores) - min(scores))
    assert worst < 1.0, (
        f"at w_cut={w_cut} territory alone swings the score by {worst:.2f}, which "
        "is a whole step of pursuit - it can overturn the distance ladder")


def test_the_live_position_the_police_stood_still_on(played):
    """C001 g01 step 10, replayed. Raw says STAY; normalised says close."""
    board = Board(SIZE)
    own, quarry = LIVE
    w_cut = played.w_cut
    raw = min(board.legal_moves(own),
              key=lambda m: _score(board, own, quarry, m, 0.959542, normalised=False))
    fixed = min(board.legal_moves(own),
                key=lambda m: _score(board, own, quarry, m, w_cut, normalised=True))
    assert raw == "STAY", (
        "this is the bug being pinned: under the shipped raw count, standing "
        "still scored -36.4 against -25.9 for closing")
    to_quarry = bfs_distances(board, quarry)
    assert to_quarry[target_of(own, fixed)] < to_quarry[own], (
        f"the fixed term chose {fixed}, which does not close the gap")


def test_the_pool_can_tell_a_pursuer_from_a_camper(played):
    """`evader` is the only sparring partner that punishes standing still.

    Everything else in the pool walks into a stationary police, which is how a
    100% lab capture rate coexisted with 0 captures in 6 counted sub-games. A
    pool that cannot see the difference will search its way back to camping.
    """
    shared = default_shared()
    doctrine = played
    camping = dataclasses.replace(doctrine, w_cut=doctrine.w_cut * AREA)  # the raw scale
    seeds = range(9000, 9020)

    def rate(doc, make_thief) -> float:
        caught = sum(sub_game(shared, ours(POLICE, doc), make_thief(), seed,
                              bool(i % 2))[0] == CAPTURE
                     for i, seed in enumerate(seeds))
        return caught / len(list(seeds))

    assert rate(camping, lambda: BUILTIN["greedy"].make(THIEF)) == 1.0, (
        "the old pool rewarded camping with a perfect score - that is why it won "
        "the search")
    assert rate(camping, Evader) == 0.0, (
        "the evader must punish camping completely, the way the league did")
    assert rate(doctrine, Evader) > 0.0, (
        "and the shipped doctrine must convert against it at all")


def test_the_barrier_is_the_only_thing_that_ever_converts_against_an_evader(played):
    """Why the fix is a rescale and not a deletion.

    An evader that refuses every cell the pursuer can reach in one step cannot
    be caught by walking: it moves first, so a cell two steps away is a cell it
    holds forever, and the gap parks at 2 exactly as it did in both counted
    losses. Measured over 200 seeds, capture rate against `evader`:

        shipped (territory rescaled, barriers on)   25.5%
        no barriers at all                           0.0%
        no squeeze, kill-shot only                   0.0%
        no kill-shot, squeeze only                   0.0%
        w_cut = 0, pure distance chase               0.0%

    Both halves are load-bearing and neither is sufficient. Territory at the
    right weight is what walks the police into barrier range; the barrier is
    what ends it. That is also why the answer to the camping bug was to divide
    `cut` rather than to drop it - at w_cut = 0 the police barely converts at
    all, which is nearly the same 0 the league gave us for the opposite reason.

    Two of those zeroes are no longer exactly zero, and the reason is worth
    keeping. Turning the police's mixing on (`police_mix_margin`, 0.0 -> 0.05
    here) lifts the pure chase from 0% to about 7%, because `Evader` refuses
    cells the pursuer can reach *given where it is now* - a rule that assumes a
    pursuer taking its best step. A pursuer that sometimes does not is a pursuer
    that rule does not fully answer. So these are asserted as fractions of the
    shipped pair rather than as absolutes: the claim being guarded is that
    neither half alone comes close, not that either is inert.

    Forty seeds here rather than 200, and only the two extremes, because this is
    a regression guard rather than the measurement itself.
    """
    shared = default_shared()
    doctrine = played
    seeds = range(9000, 9040)

    def rate(doc) -> float:
        caught = sum(sub_game(shared, ours(POLICE, doc), Evader(), seed,
                              bool(i % 2))[0] == CAPTURE
                     for i, seed in enumerate(seeds))
        return caught / len(list(seeds))

    shipped = rate(doctrine)
    assert shipped > 0.0, "the shipped pair converts"

    chase = rate(dataclasses.replace(doctrine, w_cut=0.0))
    assert chase < shipped / 2, (
        f"a pure distance chase converts {chase:.0%} against an evader, against "
        f"{shipped:.0%} for the shipped pair - territory is what closes the gap "
        "to barrier range")

    walled_off = rate(dataclasses.replace(doctrine, belief_floor=1.1, endgame_reserve=14))
    assert walled_off < shipped / 2, (
        f"with every barrier path shut off the police converts {walled_off:.0%} "
        f"against {shipped:.0%} - the barrier is what ends it")


def test_claiming_every_turn_tells_the_thief_exactly_where_we_are(played):
    """The second defect the counted losses were hiding, and it is a config value.

    A capture claim names the cell the claimant is standing on, and
    `turn_engine._answer_claim` is explicit that the answering side collapses its
    belief to a delta there. So `always_claim` does not merely ask a question
    every turn - it *answers* one, for free, in the thief's favour.

    Under `book_v1` the thief's own fix lags a turn, so the claim is the whole
    leak. Measured over 100 hold-out seeds against `evader`, police capture rate
    goes 35% -> 0% with it on, and gal-roy1 was played on `book_v1` with it on
    and converted 0 of 3. Under subtractive it costs nothing (21% -> 23%),
    because the thief can invert our served field anyway - which is why
    uoh-ay26's 0 of 3 has a different cause entirely.

    It was set as an UNCONFIRMED hedge against forfeiting a capture the opponent
    would only settle by claim-and-response. v6 closed that: `should_claim`
    already fires whenever the tracker puts the thief on the cell we just took.
    Every counted match we played without it converted 3 of 3; every one with it
    converted 0 or 1 of 3.
    """
    shared = default_shared()
    seeds = range(9100, 9140)

    def rate(always_claim: bool) -> float:
        caught = sum(sub_game(shared, ours(POLICE, played), Evader(), seed,
                              always_claim)[0] == CAPTURE for seed in seeds)
        return caught / len(list(seeds))

    assert rate(False) > 0.0, "the police must convert against an evader at all"
    # Not asserted as an inequality under subtractive: there the leak is free,
    # the two regimes are within noise of each other, and pinning an ordering
    # that noise decides is how a test starts failing for no reason.
    assert {value.strip() for value in _contract_claim_settings()} == {"false"}, (
        "no signed contract may switch it back on without re-measuring the above")


def _contract_claim_settings() -> list[str]:
    from pathlib import Path
    out = []
    for env in sorted(Path("config/opponents").glob("*.env")):
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("P2P_ALWAYS_CLAIM="):
                out.append(line.split("=", 1)[1])
    return out
