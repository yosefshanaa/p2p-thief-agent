"""Behaviour cloning: read a played match, recover a policy that can play back.

This is the half of the learning loop that makes it worth doing at all, so the
tests cover the two dialects a league actually produces and the one property
that says the fitter works: a policy generated from known weights must be
recoverable from nothing but the moves it made.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from p2p_pursuit.domain.board import Board
from p2p_pursuit.learn import clone_data, clone_fit
from p2p_pursuit.learn.clone_data import Sample

MATCH = Path("matches/warmup-reference-interop")


def native(step, pos_before, pos_after, move, barrier=None):
    return {"kind": "step", "role": "police", "step": step, "pos_before": list(pos_before),
            "pos_after": list(pos_after), "move": move, "barrier": barrier}


def reference(step, position, move, barriers="[]"):
    """The reference peer's envelope: payload + nonce + commit.

    Directions travel as ``MOVE:S``; a move that already carries its own verb
    (``HOLD:-``, their STAY) is passed through untouched.
    """
    wire = move if ":" in move else f"MOVE:{move}"
    return {"payload": {"step": step, "position": list(position), "move": wire,
                        "state": f"grid=7x7;self={list(position)};barriers={barriers}"},
            "nonce": "n", "commit": "c"}


def test_it_reads_the_reference_dialect():
    log = {"perspective": "police",
           "my_records": [native(1, (0, 0), (1, 0), "S"), native(2, (1, 0), (1, 1), "E")],
           "opponent_records": [reference(1, (4, 3), "S"), reference(2, (5, 3), "S"),
                                reference(3, (5, 4), "E")]}
    samples = clone_data.samples_from_log(log)
    assert [s.move for s in samples] == ["S", "E"]
    assert samples[0].pos == (4, 3) and samples[0].role == "thief"
    assert samples[0].pursuer == (1, 0), "their choice answered where we then stood"
    assert samples[1].prev_move == "S"


def test_it_reads_our_own_dialect_too():
    """Two of our peers can be scheduled against each other; the extractor must
    not depend on the opponent running the reference implementation."""
    log = {"perspective": "thief",
           "my_records": [native(1, (3, 3), (3, 4), "E")],
           "opponent_records": [{**native(1, (0, 0), (1, 0), "S"), "role": "police"},
                                {**native(2, (1, 0), (2, 0), "S"), "role": "police"}]}
    samples = clone_data.samples_from_log(log)
    assert [(s.role, s.pos, s.move) for s in samples] == [("police", (1, 0), "S")]


def test_barriers_are_recovered_from_both_places():
    log = {"perspective": "police",
           "my_records": [native(1, (0, 0), (1, 0), "STAY", barrier=[2, 2])],
           "opponent_records": [reference(1, (4, 3), "S"),
                                reference(2, (5, 3), "S", barriers="[[6, 6]]")]}
    walls = clone_data.samples_from_log(log)[0].barriers
    assert (2, 2) in walls and (6, 6) in walls


def test_their_hold_notation_is_a_stay_not_a_dropped_record():
    """`HOLD:-` is the reference peer's STAY. Measured on a real warm-up it was
    23 of 35 records in one sub-game, and dropping it does more than lose data:
    the surviving sample had no STAY in it at all, so a clone fitted on it would
    have learned an opponent that never holds - while the real one sat on a
    single cell for 23 consecutive turns.
    """
    log = {"perspective": "police",
           "my_records": [native(1, (0, 0), (1, 0), "S"), native(2, (1, 0), (1, 1), "E"),
                          native(3, (1, 1), (2, 1), "S")],
           "opponent_records": [reference(1, (4, 3), "S"), reference(2, (5, 3), "HOLD:-"),
                                reference(3, (5, 3), "HOLD:-"), reference(4, (5, 3), "E")]}
    samples = clone_data.samples_from_log(log)
    assert [s.move for s in samples] == ["STAY", "STAY", "E"]


def test_a_malformed_record_is_skipped_not_fatal():
    """A foreign peer decides its own record shape; one odd row must not cost
    us the other two hundred."""
    log = {"perspective": "police", "my_records": [native(1, (0, 0), (1, 0), "S")],
           "opponent_records": [{"payload": {"step": 1, "move": "TELEPORT"}},
                                reference(2, (4, 3), "S"), reference(3, (5, 3), "E")]}
    assert [s.move for s in clone_data.samples_from_log(log)] == ["E"]


def test_the_real_warm_up_match_yields_a_usable_trajectory():
    """The live interop match against the reference peer, read back off disk."""
    samples = clone_data.samples_from_match(MATCH)
    assert len(samples) >= 10
    assert {s.role for s in samples} == {"thief"}
    board = Board(7)
    for sample in samples:
        assert sample.move in board.legal_moves(sample.pos)


def test_the_fitter_recovers_a_policy_from_its_moves_alone():
    """The property that makes cloning meaningful: given only the moves a linear
    policy made, the search must find weights that reproduce them."""
    truth = dict.fromkeys(clone_fit.FEATURES, 0.0)
    truth.update({"pursuer_dist": 3.0, "mobility": 1.5, "edge": -2.0})
    rng = random.Random(11)
    samples, previous = [], None
    for _ in range(40):
        pos = (rng.randrange(7), rng.randrange(7))
        pursuer = (rng.randrange(7), rng.randrange(7))
        move = clone_fit._best_move(Board(7), pos, pursuer, previous, truth)
        samples.append(Sample(role="thief", pos=pos, pursuer=pursuer, barriers=(),
                              move=move, prev_move=previous, size=7))
        previous = move
    weights, agreed = clone_fit.fit(samples, generations=10, population=24, seed=2)
    assert agreed >= 0.9, f"recovered only {agreed:.0%} of a policy in its own model class"
    assert clone_fit.agreement(weights, samples) == agreed


def test_an_empty_match_produces_no_clone_rather_than_a_random_one():
    weights, agreed = clone_fit.fit([])
    assert agreed == 0.0
    assert set(weights) == set(clone_fit.FEATURES)


def test_a_clone_joins_the_pool_only_in_the_role_it_was_seen_in(tmp_path):
    """A team we only ever met as a thief tells us nothing about its police, and
    an unfitted all-zero weight vector is not a neutral opponent - it is a
    degenerate one that plays the same move every turn."""
    from p2p_pursuit.learn.population import build

    fitted = {"team": "rival", "samples": 40, "agreement": {"thief": 0.8},
              "weights": {"thief": dict.fromkeys(clone_fit.FEATURES, 0.5)}}
    (tmp_path / "rival.json").write_text(json.dumps(fitted), encoding="utf-8")
    member = build(("clone:rival",), directory=tmp_path)["clone:rival"]
    assert member.roles == ("thief",)
    assert isinstance(member.make("thief"), clone_fit.ClonedBrain)
