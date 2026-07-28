"""M3 regression bounds vs random baselines + network chaos drills."""

import threading
import time
from dataclasses import replace
from pathlib import Path

from p2p_pursuit.domain.brains_base import BrainBase
from p2p_pursuit.domain.rules import Decision
from p2p_pursuit.infra.transport import DirectLink, LinkError
from p2p_pursuit.peer.deadline import DeadlineTracker
from p2p_pursuit.peer.local_match import play_sub_game
from p2p_pursuit.peer.runtime import PeerRuntime
from p2p_pursuit.peer.turn_engine import TurnEngine
from tests.conftest import make_peer, make_shared

BASE = Path(__file__).resolve().parent.parent.parent


class RandomBrain(BrainBase):
    def _pick_move(self, view):
        return Decision(move=view.rng.choice(view.board.legal_moves(view.own_pos)))


def test_police_beats_random_thief():
    """Shipped police must capture a random walker in >= 7/10 seeded games."""
    shared = make_shared()
    captures = 0
    for seed in range(10):
        police = TurnEngine("police", shared, make_peer("police"), seed=seed * 2)
        thief = TurnEngine("thief", shared, make_peer("thief"), brain=RandomBrain(),
                           seed=seed * 2 + 1)
        play_sub_game(police, thief)
        captures += police.end.ending == "capture"
    assert captures >= 7, f"police regression: only {captures}/10 captures vs random"


def test_thief_survives_random_police():
    """Shipped thief must survive a random-walk police in >= 9/10 seeded games."""
    shared = make_shared()
    survivals = 0
    for seed in range(10):
        police = TurnEngine("police", shared, make_peer("police"), brain=RandomBrain(),
                            seed=seed * 2)
        thief = TurnEngine("thief", shared, make_peer("thief"), seed=seed * 2 + 1)
        play_sub_game(police, thief)
        survivals += police.end.ending == "survival"
    assert survivals >= 9, f"thief regression: only {survivals}/10 survivals vs random"


class LatencyLink(DirectLink):
    """WAN simulation: every call pays a delay both ways."""

    def __getattribute__(self, name):
        attr = super().__getattribute__(name)
        if callable(attr) and not name.startswith("_"):
            def slow(*args, **kwargs):
                time.sleep(0.02)
                return attr(*args, **kwargs)
            return slow
        return attr


def test_series_completes_under_latency(tmp_path):
    police = PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path,
                         seed=1, num_games=1)
    thief = PeerRuntime("thief", BASE / "config" / "thief", out_dir=tmp_path,
                        seed=2, num_games=1)
    assert police.connect(LatencyLink(thief.service))
    assert thief.connect(LatencyLink(police.service))
    results = {}
    threads = [threading.Thread(target=lambda: results.update(t=thief.run_series()),
                                daemon=True),
               threading.Thread(target=lambda: results.update(p=police.run_series()),
                                daemon=True)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=240)
    assert results["p"]["totals"] == results["t"]["totals"]
    assert results["p"]["sub_games"][0]["audit"] == "Verified OK"


class DeadLink(DirectLink):
    """Tunnel collapse: every call fails."""

    def commit(self, msg, timeout=None):
        raise LinkError("tunnel down")


def test_link_failure_is_clean_technical_loss(tmp_path):
    """A collapsed tunnel mid-turn ends in a technical loss, never a hang."""
    shared_dir = BASE / "config" / "police"
    rt = PeerRuntime("police", shared_dir, out_dir=tmp_path, seed=1, num_games=1)
    rt.shared = make_shared(**{"board_and_agents.first_mover": "police"})
    rt.engine.shared = rt.shared
    rt.engine.start_sub_game(1)
    rt.link = DeadLink(rt.service)  # self-link never used beyond failing commit
    rt.deadline = DeadlineTracker(timeout_sec=1, max_retries=1, backoff_sec=0,
                                  sleep=lambda s: None)
    rt.play_sub_game(1)
    assert rt.engine.end is not None
    assert rt.engine.end.ending == "technical_loss"
    assert "no response" in rt.engine.end.cause


def test_opponent_silence_is_clean_technical_loss(tmp_path):
    rt = PeerRuntime("thief", BASE / "config" / "thief", out_dir=tmp_path,
                     seed=1, num_games=1)
    rt.engine.next_mover = "police"  # opponent's turn - and they never come
    rt.peer = replace(rt.peer, turn_timeout_seconds=1)
    rt.play_sub_game(1)
    assert rt.engine.end is not None
    assert rt.engine.end.ending == "technical_loss"
    assert "turn timeout" in rt.engine.end.cause
