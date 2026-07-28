"""Full local series (determinism + audits) and a real FastMCP HTTP round-trip."""

import socket
import threading
import time

import pytest

from p2p_pursuit.peer.local_match import run_series
from tests.conftest import make_peer, make_shared


def test_full_series_deterministic_and_audited():
    shared = make_shared(**{"movement_and_barriers.max_moves": 10,
                            "movement_and_barriers.survival_threshold": 10})
    kw = {"num_games": 3, "seed": 11}
    a = run_series(shared, make_peer("police"), make_peer("thief"), **kw)
    b = run_series(shared, make_peer("police"), make_peer("thief"), **kw)
    assert [g.ending for g in a.sub_games] == [g.ending for g in b.sub_games]
    assert (a.police_total, a.thief_total) == (b.police_total, b.thief_total)
    for g in a.sub_games:
        assert g.audit_of_thief["verdict"] == "Verified OK"
        assert g.audit_of_police["verdict"] == "Verified OK"
        assert g.ending in {"capture", "survival"}
    assert a.police_total + a.thief_total > 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_mcp_http_roundtrip_full_sub_game():
    """Two real FastMCP HTTP servers on localhost play one short sub-game."""
    pytest.importorskip("fastmcp")
    from p2p_pursuit.domain import negotiation
    from p2p_pursuit.infra.mcp_client import McpLink
    from p2p_pursuit.infra.mcp_server import serve_in_thread, wait_until_up
    from p2p_pursuit.peer.service import PeerService
    from p2p_pursuit.peer.turn_engine import TurnEngine

    shared = make_shared(**{"movement_and_barriers.max_moves": 5,
                            "movement_and_barriers.survival_threshold": 5})
    ports = {"police": _free_port(), "thief": _free_port()}
    services, links = {}, {}
    for role, seed in (("police", 1), ("thief", 2)):
        peer_cfg = make_peer(role, my_port=ports[role], turn_timeout_seconds=60)
        engine = TurnEngine(role, shared, peer_cfg, seed=seed)
        hs = negotiation.handshake_payload(shared, peer_cfg, role=role, game_id="net-test",
                                           game_uid="uid", counted=False,
                                           prior_counted_games=0)
        services[role] = PeerService(engine, hs)
        serve_in_thread(services[role], host="127.0.0.1", port=ports[role],
                        name=f"test-{role}")
    links["police"] = McpLink(f"http://127.0.0.1:{ports['thief']}/mcp")
    links["thief"] = McpLink(f"http://127.0.0.1:{ports['police']}/mcp")
    assert wait_until_up(links["police"], attempts=30, delay=0.5)
    assert wait_until_up(links["thief"], attempts=30, delay=0.5)

    theirs = links["police"].handshake(services["police"].my_handshake, timeout=10)
    assert negotiation.check_compatibility(
        services["police"].my_handshake, theirs, num_games=1) == []

    def drive(role: str) -> None:
        engine, link = services[role].engine, links[role]
        while engine.end is None:
            if engine.my_turn:
                with services[role].locked():
                    package = engine.build_own_step()
                if "commit" in package:
                    link.commit(package["commit"], timeout=15)
                    with services[role].locked():
                        engine.sent_commit()
                    response = link.reveal(package["reveal"], timeout=15)
                    with services[role].locked():
                        engine.sent_reveal()
                        engine.process_reveal_response(response)
                if package.get("event"):
                    link.event(package["event"], timeout=15)
            else:
                services[role].wait_for_my_turn(30)

    threads = [threading.Thread(target=drive, args=(r,), daemon=True)
               for r in ("thief", "police")]
    for t in threads:
        t.start()
    # Hang guard, not a performance assertion: a loaded WSL host (live match +
    # capture jobs sharing the box) was observed to need >90s for the 5-move
    # roundtrip that native CI finishes in seconds.
    deadline = time.time() + 180
    while time.time() < deadline and any(
            services[r].engine.end is None for r in services):
        time.sleep(0.2)
    for role in ("police", "thief"):
        assert services[role].engine.end is not None, f"{role} never finished"

    # mutual audit over the wire
    from p2p_pursuit.peer import audit_bridge

    verdict = links["police"].audit(
        audit_bridge.audit_package(services["police"].engine), timeout=15)
    assert verdict["verdict"] == "Verified OK"
    status = links["police"].status(timeout=10)
    assert status["role"] == "thief" and "belief" in status
