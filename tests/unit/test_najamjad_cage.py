"""The cage that closed on us, as a lab opponent.

najamjad's police walls column 3, then row 3, then shuts the corner. It played
move-for-move identically in every window of every series it ran, but it is not
one opponent - it is three, and only the last one wins:

* the 2026-08-20 friendly, 11 barriers, our thief ran the full 35 steps;
* the 2026-08-21 friendlies, 12 barriers with the twelfth at `(0, 5)` on turn
  34, which seals nothing - six thief windows, six survivals, 90-30 twice;
* the counted series the same evening, the same eleven barriers with the twelfth
  moved to `(1, 4)` on turn 30. That one shuts the box five moves inside the
  survival threshold and took all three counted windows. 75-75.

So a doctrine that survives "the najamjad cage" has proved nothing unless it is
this one, and these tests pin the reproduction because the pool has twice scored
a cage that placed no barriers and reported it as evidence.

**The physics has to be set, and this file sets it.** The counted series was
played on `subtractive_chebyshev_v1` with the packet cut BEFORE the decay and on
`config/doctrine-subtractive.json`; `QUIET` reads all three from the environment
and defaults to `book_v1`, the late cut and the default doctrine. Replayed on
those defaults the same transcript ends at `(0, 5)` and our thief survives - the
cage misses by one cell, and the whole failure is invisible. Under the physics it
was actually played on it reproduces exactly: `(2, 4)`, `capture (enclosed)`,
every seed.
"""

from __future__ import annotations

from collections import deque

import pytest

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.learn.opponents import (
    NAJAMJAD_CAGE_BARRIERS,
    NAJAMJAD_CAGE_BARRIERS_FRIENDLY,
    NAJAMJAD_CAGE_MOVES,
    najamjad_cage,
)
from p2p_pursuit.learn.population import build
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine

SIZE = 7
#: Exactly the counted contract's three negotiated terms - see the module
#: docstring for what happens without them.
COUNTED_PHYSICS = {
    "P2P_SCENT_MODEL": "subtractive_chebyshev_v1",
    "P2P_SCENT_SERVE_BEFORE_DECAY": "true",
    "P2P_DOCTRINE": "config/doctrine-subtractive.json",
}


@pytest.fixture
def counted(monkeypatch):
    """Rebuild the lab peer config under the physics the series was played on.

    `QUIET` and `active()` are both resolved at import time, so setting the
    environment is not enough - they are re-derived here inside the patch.
    """
    for key, value in COUNTED_PHYSICS.items():
        monkeypatch.setenv(key, value)
    from p2p_pursuit.learn.arena import default_shared
    from p2p_pursuit.shared.config import PeerConfig
    from p2p_pursuit.shared.config_env import apply_env_overrides
    from p2p_pursuit.strategy.params import active

    peer = apply_env_overrides(PeerConfig(raw={}, group_name="lab", group_id="lab"))
    assert peer.scent_serve_before_decay, "the early cut is the whole point"
    assert peer.scent_model == "subtractive_chebyshev_v1"
    return default_shared(), peer, active()


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


def _play(counted, seed: int):
    from p2p_pursuit.learn.population import ours

    shared, peer, doctrine = counted
    police = TurnEngine(POLICE, shared, peer, brain=najamjad_cage(), seed=seed * 2)
    thief = TurnEngine(THIEF, shared, peer, brain=ours(THIEF, doctrine), seed=seed * 2 + 1)
    play_sub_game(police, thief)
    return police, thief


def test_the_transcript_lines_up_turn_for_turn() -> None:
    assert len(NAJAMJAD_CAGE_MOVES) == len(NAJAMJAD_CAGE_BARRIERS) == 30
    assert sum(b is not None for b in NAJAMJAD_CAGE_BARRIERS) == 12, "their quota spend"


def test_the_lethal_cage_differs_from_the_friendly_one_by_a_single_placement() -> None:
    """The evidence that this opponent iterates between meetings.

    Eleven barriers identical, the twelfth moved from `(0, 5)` on turn 34 to
    `(1, 4)` on turn 30 - from a cell that seals nothing to the cell that shuts
    the box, four moves earlier. Six friendly thief windows survived; three
    counted ones did not.
    """
    lethal = [b for b in NAJAMJAD_CAGE_BARRIERS if b is not None]
    friendly = [b for b in NAJAMJAD_CAGE_BARRIERS_FRIENDLY if b is not None]
    assert lethal[:11] == friendly[:11]
    assert friendly[11] == (0, 5) and lethal[11] == (1, 4)
    assert NAJAMJAD_CAGE_BARRIERS.index((1, 4)) < NAJAMJAD_CAGE_BARRIERS_FRIENDLY.index((0, 5))


def test_it_is_in_the_pool_as_a_police_only_member() -> None:
    pool = build()
    assert "najamjad-cage" in pool
    assert pool["najamjad-cage"].roles == (POLICE,), "it is a pursuer transcript"


def test_it_places_every_one_of_its_twelve_barriers(counted) -> None:
    """`cager` shipped twice having placed none at all. Count them, always."""
    police, _ = _play(counted, 0)
    assert len(police.board.barriers) >= 12, (
        f"the cage placed {len(police.board.barriers)} barriers - a statue, not a cage")


def test_it_seals_our_thief_completely(counted) -> None:
    """The counted outcome, reproduced: 49 reachable cells down to one."""
    for seed in range(5):
        police, thief = _play(counted, seed)
        pocket = _region(thief.own_pos, set(police.board.barriers))
        assert len(pocket) == 1, f"seed {seed}: pocket was {len(pocket)} cells, cage did not shut"


def test_it_kills_our_thief_on_the_cell_it_killed_it_on(counted) -> None:
    """The regression this file now exists for.

    Not a near-miss any more: `(2, 4)`, `capture (enclosed)`, every seed - the
    same cell and the same cause as all three counted windows. When a doctrine
    finally beats this, THIS is the assertion that has to be inverted, and
    inverting it is the only honest evidence that the cage was solved.
    """
    for seed in range(5):
        police, thief = _play(counted, seed)
        end = police.end or thief.end
        assert end is not None and end.ending == "capture", f"seed {seed}: {end}"
        assert "enclos" in end.cause, f"seed {seed}: killed by {end.cause}, not the cage"
        assert thief.own_pos == (2, 4), f"seed {seed}: died on {thief.own_pos}"


def test_the_lab_default_physics_hides_the_whole_failure(monkeypatch) -> None:
    """Why the fixture exists, asserted rather than trusted.

    On the lab's defaults - `book_v1`, the late cut, the default doctrine - this
    same transcript ends at `(0, 5)` and our thief survives. The cage misses by
    one cell and the failure is invisible, which is exactly how it read for a
    week while every measurement of this member was taken on those defaults.

    The defaults are rebuilt here rather than read off `arena.QUIET`: that is
    resolved at import time, so whether it holds them at all depends on which
    test imported `arena` first.
    """
    for key in COUNTED_PHYSICS:
        monkeypatch.delenv(key, raising=False)
    from p2p_pursuit.learn.arena import default_shared
    from p2p_pursuit.learn.population import ours
    from p2p_pursuit.shared.config import PeerConfig
    from p2p_pursuit.shared.config_env import apply_env_overrides
    from p2p_pursuit.strategy.params import active

    peer = apply_env_overrides(PeerConfig(raw={}, group_name="lab", group_id="lab"))
    assert not peer.scent_serve_before_decay, "unset env must mean the late cut"
    shared = default_shared()
    police = TurnEngine(POLICE, shared, peer, brain=najamjad_cage(), seed=0)
    thief = TurnEngine(THIEF, shared, peer, brain=ours(THIEF, active()), seed=1)
    play_sub_game(police, thief)
    assert (police.end or thief.end).ending == "survival", (
        "if this ever starts capturing, the defaults have changed and the "
        "counted fixture is no longer measuring anything distinct")
    assert thief.own_pos != (2, 4), "the default physics walks a different path"
