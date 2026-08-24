"""The LLM police may only ever *replace* a move we already hold.

`strategy.police_llm` crosses the line every other module in the package
respects - "the move is decided before any of this runs" - so the whole of its
safety is in the fallback paths, and every one of them is pinned here. A brain
that stalls does not play a worse game, it forfeits the sub-game: `turn_engine`
gets one decision per step and there is no second chance at the deadline.
"""

from __future__ import annotations

import random

import pytest

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.brains_base import BrainView, load_brain
from p2p_pursuit.domain.rules import POLICE, Decision
from p2p_pursuit.shared.config import PeerConfig
from p2p_pursuit.shared.config_env import apply_env_overrides
from p2p_pursuit.strategy.llm_move import first_legal
from p2p_pursuit.strategy.police_brain import PoliceBrain
from p2p_pursuit.strategy.police_llm import LLMPoliceBrain

SIZE = 7


def view(pos=(0, 0), barriers=()) -> BrainView:
    board = Board(SIZE, set(barriers))
    return BrainView(
        role=POLICE, sub_game=1, step=3, own_pos=pos, board=board,
        belief=BeliefMap(size=SIZE), opp_scent=[[0.0] * SIZE for _ in range(SIZE)],
        own_scent=[[0.0] * SIZE for _ in range(SIZE)], barriers_used=0,
        barrier_quota=14, steps_remaining=30, survival_threshold=35,
        trust=1.0, map_area="urban", rng=random.Random(0))


class Stub:
    """A client that answers however the test needs it to."""

    def __init__(self, reply="", tokens=0, raises=None):
        self.reply, self.tokens, self.raises = reply, tokens, raises
        self.calls, self.last_prompt = 0, ""

    def ask(self, prompt):
        self.calls, self.last_prompt = self.calls + 1, prompt
        if self.raises is not None:
            raise self.raises
        return self.reply, self.tokens


def brain(client, **kw) -> LLMPoliceBrain:
    return LLMPoliceBrain(client=client, allow_barriers=kw.pop("allow_barriers", False))


def test_it_is_off_unless_the_strategy_section_asks_for_it():
    """Nothing in a shipped config points here, so the doctrine is what plays."""
    assert isinstance(load_brain(None, POLICE), PoliceBrain)
    assert not isinstance(load_brain(None, POLICE), LLMPoliceBrain)


def test_the_environment_can_arm_it_for_one_match(monkeypatch):
    """Arming must not require editing a committed file - see `BRAIN_CLASS_VARS`."""
    monkeypatch.setenv("P2P_POLICE_CLASS", "p2p_pursuit.strategy.police_llm:LLMPoliceBrain")
    peer = apply_env_overrides(PeerConfig(raw={}, group_name="t", group_id="t"))
    assert peer.strategy["police_class"].endswith("LLMPoliceBrain")
    assert isinstance(load_brain(peer.strategy["police_class"], POLICE), LLMPoliceBrain)


def test_no_provider_configured_means_the_doctrine_plays():
    bare = LLMPoliceBrain()
    assert not bare.live
    assert bare._decide_move(view()) == PoliceBrain()._decide_move(view())


def test_a_legal_answer_replaces_the_doctrine_move():
    subject = brain(Stub(reply="S", tokens=12))
    assert subject._decide_move(view()).move == "S"
    assert subject.moves_from_model == 1


@pytest.mark.parametrize("reply", ["NORTHEAST", "", "I refuse", "42", "{'move': 'S'}"])
def test_an_answer_that_names_no_legal_move_falls_back(reply):
    """Never coerced to the nearest match: `NORTHEAST` is not `N`."""
    subject = brain(Stub(reply=reply))
    expected = PoliceBrain()._decide_move(view())
    assert subject._decide_move(view()) == expected
    assert subject.moves_from_model == 0


@pytest.mark.parametrize("boom", [TimeoutError("slow"), RuntimeError("down"),
                                  ValueError("empty completion")])
def test_any_exception_at_all_falls_back(boom):
    subject = brain(Stub(raises=boom))
    assert subject._decide_move(view()) == PoliceBrain()._decide_move(view())


def test_three_consecutive_slow_failures_switch_the_model_off_for_good():
    """A dead endpoint costs one turn's patience, not thirty-five of them.

    Only slow failures count - see `test_a_fast_failure_costs_one_turn`. The
    stub carries a tiny `timeout` so its instant raise reads as having eaten
    the whole budget, which is what a real dead endpoint does.
    """
    stub = Stub(raises=TimeoutError("slow"))
    stub.timeout = 0.0
    subject = brain(stub)
    for _ in range(3):
        subject._decide_move(view())
    assert not subject.live
    subject._decide_move(view())
    assert stub.calls == 3, "the brain kept calling a provider it had given up on"


def test_one_success_resets_the_breaker():
    stub = Stub(reply="S")
    subject = brain(stub)
    subject._failures = 2
    subject._decide_move(view())
    assert subject._failures == 0 and subject.live


def test_a_barrier_turn_stays_with_the_doctrine(monkeypatch):
    """87% of archived thief kills are barrier kills; that logic is the tuned part."""
    wall = Decision(move="STAY", barrier=(1, 1))
    monkeypatch.setattr(PoliceBrain, "_decide_move", lambda self, v: wall)
    stub = Stub(reply="N")
    subject = brain(stub, allow_barriers=False)
    assert subject._decide_move(view()) == wall
    assert stub.calls == 0, "a barrier turn was handed to the model"


def test_a_barrier_turn_can_be_handed_over_deliberately(monkeypatch):
    """`P2P_POLICE_LLM_BARRIERS=true` is the one way past the rule above."""
    monkeypatch.setattr(PoliceBrain, "_decide_move",
                        lambda self, v: Decision(move="STAY", barrier=(1, 1)))
    stub = Stub(reply="S")           # N and W are off-board at (0, 0)
    subject = brain(stub, allow_barriers=True)
    chosen = subject._decide_move(view())
    assert chosen.move == "S" and chosen.barrier is None
    assert stub.calls == 1


def test_tokens_are_metered_once_and_then_reset():
    """`turn_engine` adds this to the sealed `tokens_used` after every decision."""
    subject = brain(Stub(reply="S", tokens=37))
    subject._decide_move(view())
    assert subject.take_tokens() == 37
    assert subject.take_tokens() == 0, "the same tokens were sealed twice"


def test_the_move_it_returns_is_always_legal_for_the_cell():
    """A wall means the model cannot talk us through it, whatever it answers."""
    walled = view(pos=(0, 0), barriers={(0, 1), (1, 0)})
    legal = walled.board.legal_moves(walled.own_pos)
    assert "E" not in legal and "S" not in legal
    subject = brain(Stub(reply="E"))
    assert subject._decide_move(walled).move in legal


@pytest.mark.parametrize(("text", "expected"), [
    ("N", "N"), ("i'll go NORTH... N.", "N"), ("**S**", "S"), ("stay", "STAY"),
    ("NORTHEAST", None), ("", None), ("north", None),
])
def test_the_reply_parser_is_lenient_about_prose_and_strict_about_the_token(text, expected):
    assert first_legal(text, ["N", "S", "E", "W", "STAY"]) == expected


def test_a_whole_sub_game_completes_with_the_provider_dead():
    """The claim this module has to earn: a dead model costs points, never the game.

    Unit fallbacks are not enough on their own - the forfeit risk lives in the
    turn loop, where one missing decision ends the sub-game. So play a real one
    against a provider that raises on every call.
    """
    from p2p_pursuit.domain.rules import THIEF
    from p2p_pursuit.learn import arena, population
    from p2p_pursuit.peer.local_match import play_sub_game
    from p2p_pursuit.peer.turn_engine import TurnEngine

    shared = arena.default_shared()
    subject = brain(Stub(raises=TimeoutError("provider down")))
    police = TurnEngine(POLICE, shared, arena.QUIET, brain=subject, seed=20)
    thief = TurnEngine(THIEF, shared, arena.QUIET,
                       brain=population.build(("evader",))["evader"].make(THIEF), seed=21)
    play_sub_game(police, thief)

    assert police.end is not None or thief.end is not None, "the sub-game never ended"
    assert subject.moves_from_model == 0 and subject.moves_from_doctrine > 0
    assert police.tokens_used == 0, "a failed call was still billed to the seal"


def test_a_proof_replaces_the_estimate_rather_than_sitting_beside_it():
    """`opp_cells` is an inverted fix; the belief map is a guess. Never averaged.

    Printing a 2% uniform smear beside a certainty is not extra evidence, it is
    an invitation to split the difference - and only one of the two is exact.
    """
    stub = Stub(reply="S")
    subject = brain(stub)
    exact = BrainView(**{**vars(view()), "opp_cells": ((3, 3),)})
    subject._decide_move(exact)
    assert "provably on one of these cells: [3, 3]" in stub.last_prompt
    assert "a guess, not a proof" not in stub.last_prompt


def test_without_a_proof_the_estimate_is_shown_and_labelled_as_one():
    stub = Stub(reply="S")
    subject = brain(stub)
    subject._decide_move(view())
    assert "a guess, not a proof" in stub.last_prompt
    assert "provably" not in stub.last_prompt


def test_the_prompt_precomputes_what_each_legal_move_does():
    """An LLM is poor at BFS over a walled grid and good at picking a number."""
    stub = Stub(reply="S")
    subject = brain(stub)
    exact = BrainView(**{**vars(view()), "opp_cells": ((3, 3),)})
    subject._decide_move(exact)
    assert "S    -> you stand on [1, 0], thief 5 steps away" in stub.last_prompt
    assert "STAY -> you stand on [0, 0], thief 6 steps away" in stub.last_prompt


def test_the_prompt_carries_history_the_board_cannot_show():
    """Every call is stateless, so anything not written down does not exist.

    A move list alone is not enough: "S, E, STAY, STAY" cannot tell the model it
    has been parked in a corner for four turns, which is the failure the live
    archive actually shows. Three things go in - our path, the opponent's path,
    and the order walls appeared.
    """
    stub = Stub(reply="S")
    # allow_barriers so every turn reaches the model: on a barrier turn the
    # police returns early and the prompt under test would be a stale one.
    subject = brain(stub, allow_barriers=True)
    subject._decide_move(view())
    assert "This is your first move." in stub.last_prompt

    for step, (mine, theirs) in enumerate(
            [((0, 0), (3, 3)), ((0, 1), (3, 2)), ((0, 2), (3, 1))], start=1):
        board = view(pos=mine, barriers={(5, 5)} if step > 1 else ())
        subject._decide_move(BrainView(**{**vars(board), "opp_cells": (theirs,)}))
    prompt = stub.last_prompt
    assert "Your path so far (oldest first): [0, 0] -> [0, 0] -> [0, 1] -> [0, 2]." in prompt
    assert "Where the opponent has been (oldest first): [3, 3] -> [3, 2] -> [3, 1]." in prompt
    # `view()` fixes step=3, so that is the step the wall is recorded at.
    assert "Walls in the order they appeared: [5, 5] at step 3." in prompt


def test_sitting_in_two_cells_is_called_out_explicitly():
    """The observed failure was dithering, and a board cannot show dithering."""
    stub = Stub(reply="S")
    subject = brain(stub, allow_barriers=True)
    for pos in ((0, 0), (0, 1), (0, 0), (0, 1), (0, 0)):
        subject._decide_move(view(pos=pos))
    assert "you are not escaping, you are waiting to be caught" in stub.last_prompt


def test_an_override_records_the_move_we_actually_played():
    """`_last_move` gates the no-second-STAY rule and the backtrack tie-break.

    The doctrine sets it to *its* choice on the way past (police_brain.py:504),
    so an override that does not correct it leaves the brain reasoning about a
    move it never played.
    """
    board = view()
    doctrine = PoliceBrain()._decide_move(view()).move
    wanted = next(m for m in board.board.legal_moves(board.own_pos) if m != doctrine)
    subject = brain(Stub(reply=wanted))
    played = subject._decide_move(view())
    assert played.move == wanted
    assert subject._last_move == wanted, "the brain recorded a move it did not play"


class Cold:
    """A client that is still warming: present, but not usable yet."""

    ready = False

    def ask(self, prompt):
        raise AssertionError("a cold client must never be asked")


def test_a_warming_client_is_not_live_and_is_never_called():
    """Warm-up runs on a daemon thread because it measured 35.5 s - past the
    30 s step deadline. Until it lands the doctrine plays, which costs a few
    early turns and cannot cost the sub-game."""
    subject = brain(Cold())
    assert not subject.live
    assert subject._decide_move(view()) == PoliceBrain()._decide_move(view())
    assert subject.moves_from_doctrine == 1


def test_constructing_a_client_does_not_block_the_caller():
    """The constructor must return immediately even for a real provider."""
    import time

    from p2p_pursuit.strategy.llm_move import MoveClient

    start = time.time()
    client = MoveClient("openai", "gpt-5.6-luna", timeout=1, base_url="http://127.0.0.1:1")
    assert time.time() - start < 2.0, "the constructor blocked on warm-up"
    assert not client.ready, "a client cannot be ready before its thread has run"


class Slow:
    """A client whose failures cost the clock, which is what the breaker is for."""

    timeout = 10

    def ask(self, prompt):
        import time
        time.sleep(0.06)
        raise TimeoutError("slow")


class Instant:
    """A client that fails immediately - cheap, so it must not trip the breaker."""

    timeout = 0.1

    def __init__(self):
        self.calls = 0

    def ask(self, prompt):
        self.calls += 1
        raise ValueError("empty completion")


def test_a_fast_failure_costs_one_turn_and_never_trips_the_breaker():
    """20 instant failures once cost 103 turns to `not_live` - five times the damage."""
    client = Instant()
    subject = brain(client)
    for _ in range(10):
        subject._decide_move(view())
    assert subject.live, "an instant failure tripped the breaker meant for slow ones"
    assert client.calls == 10, "the brain stopped asking a provider that costs nothing"
    assert subject.fallbacks["call_failed"] == 10
    assert subject.fallbacks["not_live"] == 0


def test_a_slow_failure_still_trips_the_breaker():
    subject = brain(Slow())
    subject._client.timeout = 0.1          # 0.06s sleep is over half of it
    for _ in range(3):
        subject._decide_move(view())
    assert not subject.live
