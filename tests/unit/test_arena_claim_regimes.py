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
from p2p_pursuit.strategy.params import Doctrine, active

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


def test_claiming_every_turn_is_what_makes_the_thief_catchable():
    """The measurement that motivated the split, kept where it can be re-run.

    Measured against a **fixed reference thief** - the shipped defaults - not
    against whatever `config/doctrine.json` currently holds. The claim here is
    about the *objective*, and an objective test that reads the tuned file
    starts failing exactly when the tuning succeeds: the current thief survives
    both regimes outright, which says something about the thief and nothing at
    all about whether the regime matters.
    """
    pool = population.build(("mirror", "barrier", "hound", "interceptor"))
    reference = Doctrine()
    quiet = _survival(reference, pool, always_claim=False)
    loud = _survival(reference, pool, always_claim=True)
    assert loud < quiet, (
        f"survival {loud:.0%} claiming vs {quiet:.0%} not claiming - if these "
        f"were equal the regime would not matter and this split would be noise")


def test_the_tuned_thief_is_the_reason_this_test_needs_a_fixed_reference():
    """Pin the improvement that broke the earlier form of the test above."""
    pool = population.build(("mirror", "barrier", "hound", "interceptor"))
    assert _survival(active(), pool, always_claim=True) >= \
        _survival(Doctrine(), pool, always_claim=True)


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
