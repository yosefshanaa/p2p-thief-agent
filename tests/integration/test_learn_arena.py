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


def trajectory(pool_member, role: str, seed: int = 90, against=None) -> tuple[str, ...]:
    """The moves one archetype actually plays, from a fixed opening.

    A ``stateful`` member is measured on its SECOND sub-game, because its first
    is not where its behaviour lives: `replayer` is defined entirely by what it
    does with a memory of the sub-game before, and on a cold start it correctly
    plays its parent's game. Measuring the cold start would either fail a
    de-duplication test it does not actually violate, or - worse - be silenced by
    giving the archetype a pointless opening quirk to tell it apart by. The
    objective plays it 23 sub-games warm to 1 cold, so warm is the honest sample.
    """
    from p2p_pursuit.peer.local_match import play_sub_game
    from p2p_pursuit.peer.turn_engine import TurnEngine

    shared = arena.default_shared()
    brains = {role: pool_member.make(role)}
    if against is not None:
        brains[POLICE if role == THIEF else THIEF] = against
    brains.setdefault(POLICE, population.ours(POLICE))
    brains.setdefault(THIEF, population.ours(THIEF))

    def once() -> TurnEngine:
        police = TurnEngine(POLICE, shared, arena.QUIET, brain=brains[POLICE], seed=seed)
        thief = TurnEngine(THIEF, shared, arena.QUIET, brain=brains[THIEF], seed=seed + 1)
        play_sub_game(police, thief)
        return police if role == POLICE else thief

    if getattr(pool_member, "stateful", False):
        once()
    return tuple(r["move"] for r in once().my_records if "move" in r)


def fingerprint(pool_member, role: str) -> tuple:
    """How an archetype plays against SEVERAL counterparties, not just one.

    A pursuer's behaviour is a function of the evader it faces, so one sample
    cannot tell two archetypes apart that differ only in a situation the sample
    never reaches. `sniper` bars the cell the evader is standing on, which our
    own thief never allows - it refuses to end a move inside the pursuer's reach
    - so against that one counterparty it is indistinguishable from its parent
    and against a naive one it is not. Sampling a single opponent would either
    fail this test for a member that is genuinely distinct, or push someone to
    give the archetype a cosmetic quirk purely to be told apart by, which would
    be worse than the duplicate it was hiding.
    """
    from p2p_pursuit.learn.opponents import RandomWalker

    others = (None, RandomWalker())
    return tuple(trajectory(pool_member, role, against=o) for o in others)


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
            moves = fingerprint(member, role)
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
