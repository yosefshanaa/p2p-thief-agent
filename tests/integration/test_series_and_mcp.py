"""Full local series (determinism + audits) and a real FastMCP HTTP round-trip."""

import socket
import threading

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
    # Join before auditing - the real orchestrator's ordering. Auditing on the
    # end-flags alone raced a driver's final in-flight event delivery and once
    # produced a false TAMPERED in CI (the server was one commitment short).
    # The timeout is a hang guard for loaded hosts, not a performance bound.
    for t in threads:
        t.join(timeout=180)
    assert not any(t.is_alive() for t in threads), "drive threads never finished"
    for role in ("police", "thief"):
        assert services[role].engine.end is not None, f"{role} never finished"

    # mutual audit over the wire
    from p2p_pursuit.peer import audit_bridge

    verdict = links["police"].audit(
        audit_bridge.audit_package(services["police"].engine), timeout=15)
    assert verdict["verdict"] == "Verified OK"
    status = links["police"].status(timeout=10)
    assert status["role"] == "thief" and "belief" in status


def test_the_server_answers_a_caller_that_never_opened_a_session():
    """The live forfeit, 2026-08-02. A stateful streamable-HTTP server demands
    an `initialize` handshake and an `Mcp-Session-Id` on every later request.
    Our first real opponent's client posted tool calls without one: hundreds of
    `Created new transport ... -> 400 Bad Request`, three sub-games lost to
    180 s turn timeouts, not a single move exchanged.

    Neither dialect needs the session - both are request/response tool calls and
    nothing is ever pushed server-to-client - so accepting the superset of
    clients costs nothing and is the difference between a match and a forfeit.
    """
    import json
    import time
    import urllib.error
    import urllib.request

    from p2p_pursuit.infra.mcp_server import serve_in_thread
    from p2p_pursuit.peer.service import PeerService
    from p2p_pursuit.peer.turn_engine import TurnEngine
    from tests.conftest import make_peer, make_shared

    engine = TurnEngine("police", make_shared(), make_peer("police"), seed=5)
    port = 8913
    service = PeerService(engine, {"role": "police", "sub_game": 1})
    serve_in_thread(service, host="127.0.0.1", port=port, stateless=True)
    time.sleep(5)

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "health_check", "arguments": {}}}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp", data=body,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(request, timeout=20) as response:
        assert response.status == 200, "a session-less caller must still be served"
