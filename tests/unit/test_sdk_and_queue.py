"""SDK facade, Gatekeeper overflow queue, versioned rate-limits loader."""

import json
from pathlib import Path

import pytest

from p2p_pursuit.sdk import PursuitSDK
from p2p_pursuit.shared.config import load_rate_limits
from p2p_pursuit.shared.gatekeeper import ALLOWED, QUEUE_FULL, Gatekeeper

BASE = Path(__file__).resolve().parent.parent.parent


def test_gatekeeper_queues_overflow_instead_of_dropping():
    now = {"t": 0.0}
    g = Gatekeeper(daily_quota=100, requests_per_minute=60, burst_capacity=1,
                   queue_depth=3, clock=lambda: now["t"])
    g.dos.max_in_window = 1000
    assert g.submit("r1") == ALLOWED          # spends the only token
    assert g.submit("r2") == "blocked: no rate token (back off)"
    assert list(g.queue) == ["r2"]            # queued FIFO, not dropped
    g.submit("r3")
    g.submit("r4")
    assert g.submit("r5") == QUEUE_FULL       # bounded: backpressure signal
    assert len(g.queue) == 3
    released: list[str] = []                  # capacity 1 => one release per refill
    for t in (3.0, 6.0, 9.0):
        now["t"] = t
        released += g.drain()
    assert released == ["r2", "r3", "r4"]     # FIFO order preserved
    assert not g.queue


def test_drain_respects_quota_and_lock():
    now = {"t": 0.0}
    g = Gatekeeper(daily_quota=1, requests_per_minute=600, burst_capacity=1,
                   queue_depth=5, clock=lambda: now["t"])
    g.dos.max_in_window = 1000
    assert g.submit("a") == ALLOWED           # quota now exhausted
    g.queue.append("b")
    now["t"] = 10.0
    assert g.drain() == []                    # daily quota gates the drain too


def test_load_rate_limits_and_version_validation(tmp_path):
    cfg = load_rate_limits(BASE / "config" / "police")
    assert cfg["requests_per_minute"] >= 30 and cfg["queue_depth"] >= 100
    assert load_rate_limits(tmp_path) == {}   # missing file -> defaults upstream
    bad = {"rate_limits": {"version": "2.00", "services": {"default": {}}}}
    (tmp_path / "rate_limits.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="incompatible"):
        load_rate_limits(tmp_path)


def test_sdk_runs_local_series_and_replay(tmp_path):
    from p2p_pursuit.peer import log_manager

    sdk = PursuitSDK()
    logs: list[Path] = []

    def per_sub_game(police, thief, outcome) -> None:
        log = log_manager.build_log(police, thief.my_records, game_uid="u",
                                    game_id="gid", audit={"mine_of_them": {}})
        logs.append(log_manager.write_log(log, tmp_path))

    shared, police_cfg, _t, series = sdk.run_local_series(num_games=1, seed=3,
                                                          on_sub_game=per_sub_game)
    assert series.sub_games[0].audit_of_thief["verdict"] == "Verified OK"
    view = sdk.load_replay(logs[0])
    assert view["verdict"] == "Verified OK" and view["timeline"]
    result = sdk.build_local_result(
        game_uid="u", game_id="gid", shared=shared, police_cfg=police_cfg,
        sub_games=[], police_total=series.police_total,
        thief_total=series.thief_total, tokens_used=0)
    assert result["report_type"] == "game_result"


def test_sdk_transport_pick_is_dry_run_outside_send_mode():
    from p2p_pursuit.infra.email_sender import DryRunTransport

    notes: list[str] = []
    transport = PursuitSDK().pick_email_transport("draft", notify=notes.append)
    assert isinstance(transport, DryRunTransport)
    assert any("dry-run" in n for n in notes)


def test_package_exports_version():
    import p2p_pursuit

    assert p2p_pursuit.__version__ == "1.00"
