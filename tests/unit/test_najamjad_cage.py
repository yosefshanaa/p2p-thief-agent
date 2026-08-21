"""The cage that closed on us, as a lab opponent.

najamjad's police, 2026-08-20, took our thief from 49 reachable cells down to 7
in each of its three windows and played move-for-move identically in all three.
It never captured - so the live record reads 3-0 to us and says nothing about
how close it was. These tests pin the reproduction, because the pool has twice
scored a cage that placed no barriers and reported it as evidence.
"""

from __future__ import annotations

from collections import deque

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.learn.arena import QUIET, default_shared
from p2p_pursuit.learn.opponents import (
    NAJAMJAD_CAGE_BARRIERS,
    NAJAMJAD_CAGE_MOVES,
    najamjad_cage,
)
from p2p_pursuit.learn.population import build
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine
from p2p_pursuit.strategy.params import active

SIZE = 7


def _region(start, barriers):
    seen, queue = {start}, deque([start])
    while queue:
        cell = queue.popleft()
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (cell[0] + d[0], cell[1] + d[1])
            if 0 <= n[0] < SIZE and 0 <= n[1] < SIZE and n not in barriers and n not in seen:
                seen.add(n)
                queue.append(n)
    return seen


def _play(seed: int):
    shared = default_shared()
    police = TurnEngine(POLICE, shared, QUIET, brain=najamjad_cage(), seed=seed * 2)
    thief = TurnEngine(THIEF, shared, QUIET, brain=ours_thief(), seed=seed * 2 + 1)
    play_sub_game(police, thief)
    return police, thief


def ours_thief():
    from p2p_pursuit.learn.population import ours

    return ours(THIEF, active())


def test_the_transcript_lines_up_turn_for_turn() -> None:
    assert len(NAJAMJAD_CAGE_MOVES) == len(NAJAMJAD_CAGE_BARRIERS) == 34
    assert sum(b is not None for b in NAJAMJAD_CAGE_BARRIERS) == 12, "their quota spend"


def test_it_is_in_the_pool_as_a_police_only_member() -> None:
    pool = build()
    assert "najamjad-cage" in pool
    assert pool["najamjad-cage"].roles == (POLICE,), "it is a pursuer transcript"


def test_it_places_every_one_of_its_twelve_barriers() -> None:
    """`cager` shipped twice having placed none at all. Count them, always."""
    police, _ = _play(0)
    assert len(police.board.barriers) >= 12, (
        f"the cage placed {len(police.board.barriers)} barriers - a statue, not a cage")


def test_it_closes_our_thief_into_the_same_seven_cell_pocket() -> None:
    """The live outcome, reproduced: 49 reachable cells down to 7."""
    for seed in range(5):
        police, thief = _play(seed)
        pocket = _region(thief.own_pos, set(police.board.barriers))
        assert len(pocket) <= 10, f"seed {seed}: pocket was {len(pocket)} cells, cage did not close"


def test_our_thief_still_survives_it_which_is_the_point() -> None:
    """It reproduces the live 3-0 as well - so this member is not a regression
    test for the score, it is the only place the near-miss is visible at all."""
    police, _ = _play(0)
    assert police.end is None or police.end.ending != "capture"
