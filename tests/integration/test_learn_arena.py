"""The evaluation harness: it must measure the league's objective, not a proxy.

Every number the tuner reports comes through here, so a defect in this file
would not fail loudly - it would ship a confidently wrong doctrine.
"""

from __future__ import annotations

import pytest

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.domain.scoring import CAPTURE, SURVIVAL, TECHNICAL_LOSS
from p2p_pursuit.learn import arena, population
from p2p_pursuit.strategy.params import Doctrine

SEEDS = (3101, 3102, 3103)
ENDINGS = (CAPTURE, SURVIVAL, TECHNICAL_LOSS)


@pytest.fixture(scope="module")
def pool():
    return population.build(("random", "greedy", "holder"))


def trajectory(pool_member, role: str, seed: int = 90) -> tuple[str, ...]:
    """The moves one archetype actually plays, from a fixed opening."""
    from p2p_pursuit.peer.local_match import play_sub_game
    from p2p_pursuit.peer.turn_engine import TurnEngine

    shared = arena.default_shared()
    brains = {role: pool_member.make(role)}
    brains.setdefault(POLICE, population.ours(POLICE))
    brains.setdefault(THIEF, population.ours(THIEF))
    police = TurnEngine(POLICE, shared, arena.QUIET, brain=brains[POLICE], seed=seed)
    thief = TurnEngine(THIEF, shared, arena.QUIET, brain=brains[THIEF], seed=seed + 1)
    play_sub_game(police, thief)
    mine = police if role == POLICE else thief
    return tuple(r["move"] for r in mine.my_records if "move" in r)


def test_a_sub_game_ends_and_pays_the_configured_table(pool):
    shared = arena.default_shared()
    table = shared.scoring
    ending, police, thief = arena.sub_game(
        shared, population.ours(POLICE), pool["random"].make(THIEF), seed=SEEDS[0])
    assert ending in ENDINGS
    if ending == CAPTURE:
        assert (police, thief) == (table["capture_cop"], table["capture_thief"])
    elif ending == SURVIVAL:
        assert (police, thief) == (table["survival_cop"], table["survival_thief"])


def test_the_score_is_points_not_capture_rate(pool):
    """Capture rate would rank a doctrine that never survives above one that
    always does; the table pays 20/5 as police and 5/10 as thief."""
    report = arena.score(Doctrine(), pool, SEEDS)
    as_police = sum(THIEF in m.roles for m in pool.values())
    as_thief = sum(POLICE in m.roles for m in pool.values())
    assert report.police_sub_games == as_police * len(SEEDS)
    assert report.thief_sub_games == as_thief * len(SEEDS)
    lowest, highest = min(report.per_opponent.values()), max(report.per_opponent.values())
    assert lowest <= report.points <= highest


def test_a_one_sided_archetype_is_only_played_on_its_own_side(pool):
    """``holder`` is an evader; using it as a police would score us against a
    plain gradient chaser under a second name and double that one's weight."""
    assert population.BUILTIN["holder"].roles == (THIEF,)
    report = arena.score(Doctrine(), pool, SEEDS, roles=(THIEF,))
    assert "holder" not in report.per_opponent
    assert report.police_sub_games == 0


def test_narrowing_the_roles_only_plays_that_role(pool):
    """A police-only search must not spend half its budget re-measuring a thief
    that no key in the search can change."""
    report = arena.score(Doctrine(), pool, SEEDS, roles=(POLICE,))
    assert report.thief_sub_games == 0
    assert report.police_sub_games == sum(THIEF in m.roles for m in pool.values()) * len(SEEDS)


def test_evaluation_is_reproducible(pool):
    """Common random numbers: two candidates can only be compared if the same
    seed means the same game. A drifting global rng would break the search."""
    assert arena.score(Doctrine(), pool, SEEDS).points == \
        arena.score(Doctrine(), pool, SEEDS).points


def test_no_two_archetypes_play_the_same_game_on_the_same_side():
    """The pool's whole purpose. Two members that behave alike in a role weight
    that behaviour twice in the objective - which is how a doctrine over-fits
    one evader and posts 90-98% in simulation against 0/5 on the wire.

    The de-duplication is declared in ``Member.roles``; this asserts it is
    still true of the code rather than only of the comment.
    """
    for role in (POLICE, THIEF):
        seen: dict[tuple[str, ...], str] = {}
        for name, member in population.build().items():
            if role not in member.roles:
                continue
            moves = trajectory(member, role)
            assert moves not in seen, f"{name} plays {seen[moves]}'s game as {role}"
            seen[moves] = name


def test_every_archetype_is_playable_in_the_roles_it_claims():
    shared = arena.default_shared()
    for name, member in population.build().items():
        for role in member.roles:
            other = population.ours(POLICE if role == THIEF else THIEF)
            pair = (member.make(POLICE), other) if role == POLICE else (other, member.make(THIEF))
            ending, _, _ = arena.sub_game(shared, *pair, seed=4242)
            assert ending in ENDINGS, f"{name} as {role}"


def test_the_shipped_doctrine_still_beats_a_random_walker():
    """The regression gate the doctrine has always had, restated in points."""
    report = arena.score(Doctrine(), population.build(("random",)), tuple(range(4200, 4210)))
    assert report.points > 10.0, "a random opponent must not hold us to a draw"


def test_the_worker_entry_point_takes_names_not_closures():
    """Factories are lambdas and do not pickle; the task must survive a fork."""
    import pickle

    task = (Doctrine(), ("random",), SEEDS, (POLICE,))
    assert arena.points_for(pickle.loads(pickle.dumps(task))) >= 0.0
