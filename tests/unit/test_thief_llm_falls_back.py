"""The LLM thief, and the bookkeeping an override must not corrupt.

`strategy.thief_llm` has the same contract as its police twin - the model may
only replace a move the doctrine already holds - but the thief keeps state while
it decides. `_last_move` gates the "never STAY twice" rule and `_run_len` feeds
the juke, and the doctrine sets both to *its* choice on the way past. Overriding
the move without correcting them leaves the brain reasoning about a move it
never played, which is the sort of thing that shows up six sub-games later as an
inexplicable repeat.
"""

from __future__ import annotations

import random

import pytest

from p2p_pursuit.domain.belief import BeliefMap
from p2p_pursuit.domain.board import Board
from p2p_pursuit.domain.brains_base import BrainView, load_brain
from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.shared.config import PeerConfig, apply_env_overrides
from p2p_pursuit.strategy.thief_brain import ThiefBrain
from p2p_pursuit.strategy.thief_llm import LLMThiefBrain

SIZE = 7


def view(pos=(3, 3), barriers=(), step=3) -> BrainView:
    board = Board(SIZE, set(barriers))
    return BrainView(
        role=THIEF, sub_game=1, step=step, own_pos=pos, board=board,
        belief=BeliefMap(size=SIZE), opp_scent=[[0.0] * SIZE for _ in range(SIZE)],
        own_scent=[[0.0] * SIZE for _ in range(SIZE)], barriers_used=2,
        barrier_quota=14, steps_remaining=30, survival_threshold=35,
        trust=1.0, map_area="urban", rng=random.Random(0))


class Stub:
    def __init__(self, reply="", tokens=0, raises=None):
        self.reply, self.tokens, self.raises = reply, tokens, raises
        self.calls, self.last_prompt = 0, ""

    def ask(self, prompt):
        self.calls, self.last_prompt = self.calls + 1, prompt
        if self.raises is not None:
            raise self.raises
        return self.reply, self.tokens


def doctrine_move(v: BrainView) -> str:
    return ThiefBrain()._pick_move(v).move


def other_legal(v: BrainView) -> str:
    """A legal move the doctrine did *not* pick, so an override is observable."""
    return next(m for m in v.board.legal_moves(v.own_pos) if m != doctrine_move(v))


def test_it_is_off_unless_the_strategy_section_asks_for_it():
    assert isinstance(load_brain(None, THIEF), ThiefBrain)
    assert not isinstance(load_brain(None, THIEF), LLMThiefBrain)


def test_the_environment_can_arm_it_for_one_match(monkeypatch):
    monkeypatch.setenv("P2P_THIEF_CLASS", "p2p_pursuit.strategy.thief_llm:LLMThiefBrain")
    peer = apply_env_overrides(PeerConfig(raw={}, group_name="t", group_id="t"))
    assert isinstance(load_brain(peer.strategy["thief_class"], THIEF), LLMThiefBrain)


def test_no_provider_configured_means_the_doctrine_plays():
    bare = LLMThiefBrain()
    assert not bare.live
    assert bare._pick_move(view()).move == doctrine_move(view())


def test_a_legal_answer_replaces_the_doctrine_move():
    wanted = other_legal(view())
    subject = LLMThiefBrain(client=Stub(reply=wanted), only_when_caged=False)
    assert subject._pick_move(view()).move == wanted
    assert subject.moves_from_model == 1


@pytest.mark.parametrize("reply", ["NORTHEAST", "", "no", "{'move': 'S'}"])
def test_an_answer_that_names_no_legal_move_falls_back(reply):
    subject = LLMThiefBrain(client=Stub(reply=reply), only_when_caged=False)
    assert subject._pick_move(view()).move == doctrine_move(view())
    assert subject.moves_from_model == 0


def test_any_exception_at_all_falls_back():
    subject = LLMThiefBrain(client=Stub(raises=TimeoutError("slow")), only_when_caged=False)
    assert subject._pick_move(view()).move == doctrine_move(view())


def test_three_consecutive_slow_failures_switch_the_model_off_for_good():
    """Only failures that cost the clock trip it - an instant one is a free retry."""
    stub = Stub(raises=TimeoutError("slow"))
    stub.timeout = 0.0               # reads as having eaten the whole budget
    subject = LLMThiefBrain(client=stub, only_when_caged=False)
    for _ in range(4):
        subject._pick_move(view())
    assert not subject.live and stub.calls == 3


def test_a_fast_failure_does_not_switch_the_thief_off():
    stub = Stub(raises=ValueError("empty completion"))
    stub.timeout = 10
    subject = LLMThiefBrain(client=stub, only_when_caged=False)
    for _ in range(8):
        subject._pick_move(view())
    assert subject.live and stub.calls == 8


def test_tokens_are_metered_once_and_then_reset():
    subject = LLMThiefBrain(client=Stub(reply=other_legal(view()), tokens=41),
                            only_when_caged=False)
    subject._pick_move(view())
    assert subject.take_tokens() == 41
    assert subject.take_tokens() == 0


def test_an_override_records_the_move_we_actually_played():
    """The bug this test exists for: `_last_move` must never be the discarded one."""
    wanted = other_legal(view())
    subject = LLMThiefBrain(client=Stub(reply=wanted), only_when_caged=False)
    played = subject._pick_move(view())
    assert played.move == wanted
    assert subject._last_move == wanted, "the brain recorded a move it did not play"


def test_a_repeat_extends_the_run_and_a_change_restarts_it():
    """`_run_len` gates the juke at thief_brain.py:157 - it counts played moves."""
    wanted = other_legal(view())
    subject = LLMThiefBrain(client=Stub(reply=wanted), only_when_caged=False)
    subject._last_move, subject._run_len = wanted, 2
    subject._pick_move(view())
    assert subject._run_len == 3

    subject = LLMThiefBrain(client=Stub(reply=wanted), only_when_caged=False)
    subject._last_move, subject._run_len = "STAY", 4
    subject._pick_move(view())
    assert subject._run_len == 1


def test_the_prompt_states_the_room_and_that_it_is_shrinking():
    """The cage is the thief's real killer and the doctrine cannot price it."""
    stub = Stub(reply="STAY")
    subject = LLMThiefBrain(client=stub, only_when_caged=False)
    subject._pick_move(view(pos=(0, 0)))
    assert "You can currently reach 49 of the 49 open cells" in stub.last_prompt

    walled = view(pos=(0, 0), barriers={(0, 2), (1, 2), (2, 2), (2, 1), (2, 0)})
    subject._pick_move(walled)
    assert "you are being enclosed" in stub.last_prompt
    assert "reach 4 of the 44 open cells, down from 49 last turn" in stub.last_prompt


def test_a_whole_sub_game_completes_with_the_provider_dead():
    from p2p_pursuit.learn import arena, population
    from p2p_pursuit.peer.local_match import play_sub_game
    from p2p_pursuit.peer.turn_engine import TurnEngine

    shared = arena.default_shared()
    subject = LLMThiefBrain(client=Stub(raises=TimeoutError("down")), only_when_caged=False)
    police = TurnEngine(POLICE, shared, arena.QUIET,
                        brain=population.build(("cager",))["cager"].make(POLICE), seed=30)
    thief = TurnEngine(THIEF, shared, arena.QUIET, brain=subject, seed=31)
    play_sub_game(police, thief)

    assert police.end is not None or thief.end is not None
    assert subject.moves_from_model == 0 and subject.moves_from_doctrine > 0
    assert thief.tokens_used == 0


def test_the_cops_remaining_quota_is_counted_from_the_board():
    """`barriers_used` is what WE spent, and a thief spends nothing.

    Reading it there told the model the cop still held all 14 walls no matter
    how many were already standing - understating the one threat that kills our
    thief 87% of the time.
    """
    stub = Stub(reply="STAY")
    subject = LLMThiefBrain(client=stub, only_when_caged=False)
    subject._pick_move(view(pos=(5, 5), barriers={(0, 3), (1, 3), (2, 3)}))
    assert "may still place 11 more walls" in stub.last_prompt


def test_the_model_is_asked_only_while_the_room_is_shrinking():
    """The one case it beats the vector at, and the only one it is spent on.

    Measured over five prompt versions: 0/8 survivals against `sniper` and
    `interceptor` where the doctrine goes 8/8, and 7.50 against 6.88 on
    `najamjad-cage`. Being better in one place is a reason to ask there, not
    everywhere.
    """
    stub = Stub(reply="STAY")
    subject = LLMThiefBrain(client=stub)

    subject._pick_move(view(pos=(3, 3)))                    # first turn: no trend yet
    assert stub.calls == 0, "the model was asked before any cage could exist"

    subject._pick_move(view(pos=(3, 3)))                    # room unchanged
    assert stub.calls == 0, "the model was asked while nothing was closing"

    walled = view(pos=(0, 0), barriers={(0, 2), (1, 2), (2, 2), (2, 1), (2, 0)})
    subject._pick_move(walled)                              # room collapses
    assert stub.calls == 1, "the model was not asked while the room was falling"


def test_the_gate_can_be_opened_for_an_experiment():
    stub = Stub(reply="STAY")
    subject = LLMThiefBrain(client=stub, only_when_caged=False)
    subject._pick_move(view())
    assert stub.calls == 1


class Sequence:
    """Answers a fixed script, one reply per call."""

    timeout = 10

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def ask(self, prompt):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply, 1


def test_a_majority_of_samples_wins(monkeypatch):
    """Self-consistency helps only if the errors are variance, not bias."""
    monkeypatch.setenv("P2P_MOVE_SAMPLES", "3")
    v = view()
    wanted = other_legal(v)
    subject = LLMThiefBrain(client=Sequence(f"MOVE: {wanted}", "MOVE: STAY",
                                            f"MOVE: {wanted}"),
                            only_when_caged=False)
    assert subject._pick_move(v).move == wanted
    assert subject._client.calls == 3


def test_a_split_vote_falls_back_to_the_doctrine(monkeypatch):
    """Three different answers is the model saying it does not know."""
    monkeypatch.setenv("P2P_MOVE_SAMPLES", "3")
    legal = view().board.legal_moves(view().own_pos)
    subject = LLMThiefBrain(client=Sequence(*(f"MOVE: {m}" for m in legal[:3])),
                            only_when_caged=False)
    # Fresh views on both sides: `view()` seeds its own rng, and scoring the
    # doctrine on the SAME view first would advance it and change the answer.
    assert subject._pick_move(view()).move == doctrine_move(view())
    assert subject.moves_from_doctrine == 1
    assert subject._client.calls == 3, "a split vote must still cost all N samples"
