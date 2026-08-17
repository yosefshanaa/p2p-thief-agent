"""Sparring partners built out of what teams actually did.

The pool had two ways to model a played team and neither suits a reactive one:
a fitted linear clone reproduces about three moves in four, and a fixed script
is only honest for a deterministic opponent - of the teams in ``matches/`` only
gal-roy1's thief and s82kma9e's police are one. `learn.recorded` keeps every
observed decision instead and replays the move played from the nearest state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.learn import population
from p2p_pursuit.learn.clone_data import Sample, samples_from_match
from p2p_pursuit.learn.recorded import Recorded, agreement, load_tables, table_from_samples

CONFIG = Path("config/opponents")


def sample(role, pos, pursuer, move, prev=None):
    return Sample(role=role, pos=pos, pursuer=pursuer, barriers=(), move=move,
                  prev_move=prev, size=7)


def test_a_state_it_observed_is_reproduced_exactly():
    rows = table_from_samples([sample(THIEF, (3, 3), (0, 0), "E"),
                               sample(THIEF, (3, 4), (0, 1), "S")])
    brain = Recorded([{**r, "pos": tuple(r["pos"]), "pursuer": tuple(r["pursuer"])}
                      for r in rows[THIEF]])
    assert brain.move_for((3, 3), (0, 0), None) == "E"
    assert brain.move_for((3, 4), (0, 1), None) == "S"


def test_an_unseen_state_falls_back_to_the_nearest_one_seen():
    rows = table_from_samples([sample(THIEF, (3, 3), (0, 0), "E"),
                               sample(THIEF, (6, 6), (0, 0), "N")])
    brain = Recorded([{**r, "pos": tuple(r["pos"]), "pursuer": tuple(r["pursuer"])}
                      for r in rows[THIEF]])
    assert brain.move_for((3, 2), (0, 0), None) == "E", "nearest by their own cell"
    assert brain.move_for((6, 5), (0, 0), None) == "N"


def test_their_own_cell_outweighs_ours():
    """A team's policy is mostly a function of the ground it is standing on."""
    rows = table_from_samples([sample(THIEF, (0, 0), (6, 6), "S"),
                               sample(THIEF, (6, 6), (0, 0), "N")])
    brain = Recorded([{**r, "pos": tuple(r["pos"]), "pursuer": tuple(r["pursuer"])}
                      for r in rows[THIEF]])
    # Standing where the first row stands, threatened from where the second was.
    assert brain.move_for((0, 0), (0, 0), None) == "S"


def test_repeated_states_collapse_and_carry_their_count():
    rows = table_from_samples([sample(THIEF, (3, 3), (0, 0), "E")] * 3
                              + [sample(THIEF, (3, 3), (0, 0), "W")])
    assert len(rows[THIEF]) == 1, "one state is one row however often it was seen"
    assert rows[THIEF][0]["move"] == "E", "the move they played most often wins"
    assert rows[THIEF][0]["weight"] == 3


def test_roles_are_kept_apart():
    rows = table_from_samples([sample(THIEF, (3, 3), (0, 0), "E"),
                               sample(POLICE, (3, 3), (0, 0), "W")])
    assert set(rows) == {THIEF, POLICE}
    assert rows[THIEF][0]["move"] == "E"
    assert rows[POLICE][0]["move"] == "W"


def test_an_empty_table_is_refused_rather_than_played_as_a_degenerate_policy():
    with pytest.raises(ValueError):
        Recorded([])


@pytest.mark.parametrize("team", ["gal-roy1", "amireman", "orcai-mj", "reference"])
def test_the_shipped_tables_load_and_report_honest_holdout_agreement(team):
    payload = json.loads((CONFIG / "recorded" / f"{team}.json").read_text(encoding="utf-8"))
    assert payload["roles"], f"{team} has no observed decisions"
    for role, score in payload["holdout_agreement"].items():
        assert 0.0 <= score <= 1.0
        assert role in payload["roles"]


def test_they_join_the_pool_in_the_roles_they_were_observed_in():
    pool = population.build()
    recorded = {name: member for name, member in pool.items()
                if name.startswith("recorded:")}
    assert len(recorded) >= 5, f"only {sorted(recorded)} loaded"
    for name, member in recorded.items():
        assert member.roles, f"{name} declares no roles"
        for role in member.roles:
            assert isinstance(member.make(role), Recorded)


def test_gal_roy1s_thief_is_reproduced_from_the_counted_match():
    """The one team whose thief is deterministic: agreement must be total."""
    samples = [s for s in samples_from_match(Path("matches/gal-roy1-counted"))
               if s.role == THIEF]
    assert samples, "the counted match must still carry their decisions"
    table = table_from_samples(samples)
    assert agreement(table[THIEF], samples) == 1.0


def test_load_tables_ignores_a_directory_that_is_not_there():
    assert load_tables(Path("config/opponents/does-not-exist")) == {}
