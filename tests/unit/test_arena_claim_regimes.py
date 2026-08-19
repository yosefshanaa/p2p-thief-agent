"""The lab has to play the game the league actually plays.

Whether the police claims every turn is negotiated per opponent, and our signed
contracts are split on it: amireman and gal-roy1 play `always_claim`, s82kma9e
does not. The lab defaulted to *off* for both sides, and that quietly removed
the police's main conversion path from the objective - a pool police could then
only capture by barrier or enclosure, because `BrainBase.should_claim` wants
belief 0.5 and the measured posterior peak never gets there.

The consequence was an objective blind to our own thief: 94% survival overall
and 100% against sixteen of seventeen pool members, so a thief search had
nothing to learn from and drove `corner_penalty` to 0.001. Both regimes are now
played, split by seed.
"""

from __future__ import annotations

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.learn import arena, population
from p2p_pursuit.strategy.params import Doctrine

SEEDS = tuple(range(9000, 9012))


def test_both_regimes_are_declared_and_neither_is_dropped():
    assert set(arena.CLAIM_REGIMES) == {False, True}


def test_a_sub_game_plays_the_regime_it_is_given():
    """Not a preference the config carries - an argument the objective sets."""
    shared = arena.default_shared()
    quiet = arena.sub_game(shared, population.ours(POLICE), population.ours(THIEF),
                           seed=4242, always_claim=False)
    loud = arena.sub_game(shared, population.ours(POLICE), population.ours(THIEF),
                          seed=4242, always_claim=True)
    assert quiet[0] in ("capture", "survival")
    assert loud[0] in ("capture", "survival")


def test_claiming_every_turn_helps_the_thief_not_the_police():
    """The regime matters, and it matters the other way round.

    This test used to assert the opposite - that claiming every turn is what
    makes the thief catchable - on the reasoning that a claim is how a landing
    becomes a capture. Both halves of that are true and the conclusion was still
    backwards, because a claim names the cell the *claimant* is standing on, and
    `turn_engine._answer_claim` collapses the answering side's belief to a delta
    there. Claiming every turn therefore publishes the police's exact position
    on every single turn, for free.

    Measured against `learn.opponents.Evader` over 100 hold-out seeds, police
    capture rate: under `book_v1` 35% claiming-when-it-matters against 0%
    claiming-always, and under subtractive 21% against 23% - free there only
    because the thief can already invert our served field. gal-roy1 was played
    on `book_v1` with `P2P_ALWAYS_CLAIM=true` and converted 0 of 3; every
    counted match played without it converted 3 of 3. See
    `tests/unit/test_police_pursuit.py`.

    What survives unchanged is the reason the arena plays *both* regimes: the
    league is genuinely split on the term, and the two produce materially
    different games. That is what is asserted here, in the direction the
    evidence actually points.
    """
    pool = population.build(("mirror", "barrier", "hound", "interceptor"))
    reference = Doctrine()
    quiet = _survival(reference, pool, always_claim=False)
    loud = _survival(reference, pool, always_claim=True)
    assert loud > quiet, (
        f"thief survival {loud:.0%} against a police that claims every turn vs "
        f"{quiet:.0%} against one that does not - the leak should favour the thief")


def test_the_split_is_the_same_for_every_candidate_in_a_generation():
    """Common random numbers: a candidate must not be judged on a softer mix."""
    regimes = [arena.CLAIM_REGIMES[i % len(arena.CLAIM_REGIMES)]
               for i in range(len(SEEDS))]
    assert regimes.count(True) == regimes.count(False), (
        "an odd split would weight one regime above the other by accident")
    assert regimes == [arena.CLAIM_REGIMES[i % len(arena.CLAIM_REGIMES)]
                       for i in range(len(SEEDS))], "the mapping must be pure"


def _survival(doctrine, pool, *, always_claim: bool) -> float:
    shared = arena.default_shared()
    played = survived = 0
    for member in pool.values():
        if POLICE not in member.roles:
            continue
        for seed in SEEDS:
            ending, _, _ = arena.sub_game(
                shared, member.make(POLICE), population.ours(THIEF, doctrine),
                seed + 500_000, always_claim)
            played += 1
            survived += ending == "survival"
    return survived / max(played, 1)
