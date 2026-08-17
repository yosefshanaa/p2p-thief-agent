"""The fix has to survive the foreign dialect, not just our own engine.

Everything a real opponent sends arrives as their `TurnMessage`, whose scent is
a **sparse** ``smell_grid`` of ``"r,c": value`` pairs. The tracker inverts a
dense field, so the whole finding rests on the bridge rehydrating that grid
faithfully - and on the tracker saying nothing at all when a peer sends no grid,
which is a case we have actually met on the wire.
"""

from __future__ import annotations

from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.scent import BOOK_V1, SUBTRACTIVE_V1, ScentField
from p2p_pursuit.domain.tracking import OpponentTracker
from p2p_pursuit.infra.interop_codec import from_turn_message, scent_to_grid

SIZE = 7
WALK = [(3, 3), (4, 3), (4, 4), (5, 4), (5, 5), (4, 5), (3, 5), (3, 4)]


def their_turns(model: str, walk: list[tuple[int, int]]) -> list[dict]:
    """What their peer would put on the wire, walking ``walk``."""
    field = ScentField(SIZE, model=model)
    return [{"sender": "thief", "step": i + 1, "hint": "", "commit": "",
             "smell_grid": scent_to_grid(field.serve_for_step(cell))}
            for i, cell in enumerate(walk)]


def track(model: str, messages: list[dict]) -> list:
    board = Board(SIZE)
    tracker = OpponentTracker(SIZE, model)
    out = []
    for message in messages:
        reveal = from_turn_message(message, sub_game=1, grid_size=SIZE)["reveal"]
        out.append(tracker.observe(reveal["scent"], board))
    return out


def test_a_sparse_smell_grid_still_gives_an_exact_fix():
    fixes = track(BOOK_V1, their_turns(BOOK_V1, WALK))
    found = [f for f in fixes if f is not None]
    assert found, "no fix survived the round trip through their dialect"
    assert found == WALK[1:1 + len(found)], f"got {found}"


def test_the_round_trip_is_lossless_for_every_model():
    for model in (BOOK_V1, SUBTRACTIVE_V1):
        messages = their_turns(model, WALK)
        field = ScentField(SIZE, model=model)
        for message, cell in zip(messages, WALK, strict=True):
            dense = from_turn_message(message, sub_game=1, grid_size=SIZE)["reveal"]["scent"]
            assert dense == field.serve_for_step(cell), f"{model} lost precision on the wire"


def test_a_peer_that_sends_no_grid_produces_no_fix_rather_than_a_wrong_one():
    """Measured live: some peers send the field on the turn message, some do not.

    The bridge substitutes an empty grid for a missing `smell_grid`, and a brain
    acts on a fix as confidently as on a certainty - so silence has to stay
    silence all the way through.
    """
    silent = [{"sender": "thief", "step": i + 1, "hint": "", "commit": ""}
              for i in range(4)]
    assert track(BOOK_V1, silent) == [None] * 4


def test_a_peer_that_repeats_its_last_grid_produces_no_new_fix():
    messages = their_turns(BOOK_V1, WALK[:4])
    messages.append(dict(messages[-1], step=5))
    fixes = track(BOOK_V1, messages)
    assert fixes[-1] is None, "a resend is not a step"
