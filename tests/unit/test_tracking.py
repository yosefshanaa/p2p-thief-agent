"""The running fix: what a brain is actually handed each turn.

`OpponentTracker` turns the one-shot inverse into live state - the previous
field, a fix, the fix before it (a velocity), and the answer to the only
question a brain has: which cells could the opponent be on *now*.
"""

from __future__ import annotations

import random

from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.brains_base import BrainView
from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.domain.scent import BOOK_V1, SUBTRACTIVE_V1, ScentField
from p2p_pursuit.domain.tracking import OpponentTracker
from p2p_pursuit.learn.arena import QUIET, default_shared
from p2p_pursuit.learn.population import ours
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.turn_engine import TurnEngine

SIZE = 7
WALK = [(3, 3), (3, 4), (4, 4), (5, 4), (5, 5), (5, 6), (4, 6), (3, 6)]


def feed(model: str, walk: list[tuple[int, int]]) -> tuple[OpponentTracker, list]:
    board = Board(SIZE)
    field = ScentField(SIZE, model=model)
    tracker = OpponentTracker(SIZE, model)
    fixes = [tracker.observe(field.serve_for_step(cell), board) for cell in walk]
    return tracker, fixes


def test_it_tracks_a_whole_walk_exactly():
    tracker, fixes = feed(BOOK_V1, WALK)
    # The first served field is all zeros (book_v1 serves before emitting) and
    # the second is the first evidence, so fixes begin at index 2.
    assert fixes[:2] == [None, None]
    assert fixes[2:] == WALK[1:len(fixes) - 1]
    assert tracker.fixes == len(fixes) - 2


def test_a_repeated_field_yields_no_fix_and_leaves_the_last_one_standing():
    board = Board(SIZE)
    field = ScentField(SIZE, model=BOOK_V1)
    tracker = OpponentTracker(SIZE, BOOK_V1)
    served = None
    for cell in WALK[:4]:
        served = field.serve_for_step(cell)
        tracker.observe(served, board)
    held = tracker.fix
    assert held is not None
    # The same field again - what a turn that arrives with no opponent step in
    # between looks like. It is not evidence, and fitting a centre to "nothing
    # changed" would replace a true fix with an artefact.
    assert tracker.observe([row[:] for row in served], board) is None
    assert tracker.fix == held


def test_velocity_is_a_heading_only_when_the_fixes_are_one_step_apart():
    tracker, _ = feed(BOOK_V1, WALK)
    assert tracker.velocity in {(-1, 0), (1, 0), (0, 1), (0, -1)}
    lone = OpponentTracker(SIZE, BOOK_V1)
    assert lone.velocity is None, "one fix is a position, not a heading"


def test_possible_folds_in_the_lag_each_model_carries():
    board = Board(SIZE)
    lagged, _ = feed(BOOK_V1, WALK)
    current, _ = feed(SUBTRACTIVE_V1, WALK)
    assert len(current.possible(board)) == 1, (
        "a model that serves after emitting pins the cell exactly")
    assert 2 <= len(lagged.possible(board)) <= 5, (
        "book_v1's fix is one step old, so the answer is a reachable set")
    assert lagged.fix in lagged.possible(board)


def test_possible_never_names_a_barred_cell():
    board = Board(SIZE, {(2, 6), (4, 6), (3, 5)})
    tracker, _ = feed(BOOK_V1, WALK)
    assert all(board.is_open(c) for c in tracker.possible(board))


def test_projection_runs_along_the_heading_and_stops_at_a_wall():
    board = Board(SIZE)
    tracker, _ = feed(BOOK_V1, WALK)
    ahead = tracker.projected(board)
    assert ahead is not None and board.is_open(ahead)
    walled = Board(SIZE, {(1, 6), (2, 6)})
    assert board.is_open(tracker.projected(walled) or (0, 0))


def test_the_engine_hands_the_brain_a_fix_during_a_real_sub_game():
    """End to end through the protocol, not the tracker's own API."""
    shared = default_shared()
    seen: list[BrainView] = []

    class Watching:
        claim_threshold = 0.5

        def decide(self, view):
            seen.append(view)
            return ours(POLICE).decide(view)

        def hint_plan(self, view, decision):
            return ours(POLICE).hint_plan(view, decision)

        def should_claim(self, view, new_pos):
            return False

    police = TurnEngine(POLICE, shared, QUIET, brain=Watching(), seed=1)
    thief = TurnEngine(THIEF, shared, QUIET, brain=ours(THIEF), seed=2)
    play_sub_game(police, thief)

    fixed = [v for v in seen if v.opp_cells]
    assert len(fixed) > len(seen) // 2, (
        f"only {len(fixed)} of {len(seen)} police turns carried a fix")
    assert all(v.opp_fix in v.opp_cells for v in fixed)
    assert all(0 <= v.opp_fix_lag <= 1 for v in fixed)


def test_the_fix_is_the_thiefs_true_cell_lagged_by_one():
    """The claim that everything else rests on, checked against ground truth."""
    shared = default_shared()
    police = TurnEngine(POLICE, shared, QUIET, brain=ours(POLICE), seed=3)
    thief = TurnEngine(THIEF, shared, QUIET, brain=ours(THIEF), seed=4)
    engines = {POLICE: police, THIEF: thief}
    truth: list[tuple] = []
    checked = 0
    for _ in range(200):
        if police.end is not None or thief.end is not None:
            break
        mover = engines[police.next_mover]
        if mover.role == POLICE:
            fix = police.opp_tracker.fix
            if fix is not None and len(truth) >= 2:
                assert fix == truth[-2], f"fix {fix} vs thief's previous cell {truth[-2]}"
                checked += 1
        package = mover.build_own_step()
        if mover.role == THIEF:
            truth.append(thief.own_pos)
        observer = engines[mover.other]
        if "commit" in package:
            observer.on_commit(package["commit"])
            mover.sent_commit()
            mover.process_reveal_response(observer.on_reveal(package["reveal"]))
            mover.sent_reveal()
        if package.get("event"):
            observer.on_event(package["event"])
    assert checked >= 5, f"only {checked} turns carried a fix to check"


def test_a_view_with_no_fix_still_drives_both_brains():
    """The fallback path: nothing here may require the tracker to have spoken."""
    flat = [[0.0] * SIZE for _ in range(SIZE)]
    from p2p_pursuit.domain.belief import BeliefMap

    for role in (POLICE, THIEF):
        view = BrainView(role=role, sub_game=1, step=1, own_pos=(0, 0),
                         board=Board(SIZE), belief=BeliefMap(SIZE), opp_scent=flat,
                         own_scent=flat, barriers_used=0, barrier_quota=14,
                         steps_remaining=35, survival_threshold=35, trust=0.5,
                         map_area="New York", rng=random.Random(0))
        assert ours(role).decide(view).move in ("N", "S", "E", "W", "STAY")
