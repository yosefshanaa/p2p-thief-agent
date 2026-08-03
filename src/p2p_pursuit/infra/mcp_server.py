"""FastMCP server: the tools this peer exposes to its opponent (book ch. 2).

Each agent is simultaneously a server (these tools) and a client
(mcp_client.McpLink). Binds 0.0.0.0 so a tunnel can expose it publicly.
"""

from __future__ import annotations

import threading
from typing import Any

from ..peer.service import PeerService


def _add_reference_tools(mcp: Any, bridge: Any) -> None:
    """Also answer to the reference peer's tool names, routed through the bridge."""

    @mcp.tool
    def negotiate(message: dict) -> dict:
        """Reference dialect: the opponent's signed game agreement."""
        return bridge.on_negotiate(message)

    @mcp.tool
    def receive_turn(message: dict) -> dict:
        """Reference dialect: one whole turn (commit + public reveal together)."""
        return bridge.on_receive_turn(message)

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        """Reference dialect: end-of-game reveal of records and nonces."""
        return bridge.on_submit_audit(payload)

    @mcp.tool
    def receive_control(message: dict) -> dict:
        """Reference dialect: advisory control signal (accepted, not acted on)."""
        return bridge.on_receive_control(message)


def build_server(service: PeerService, name: str = "p2p-pursuit-peer", bridge: Any = None):
    from fastmcp import FastMCP

    mcp = FastMCP(name)

    @mcp.tool
    def handshake(payload: dict) -> dict:
        """Exchange identity + constitution/scent locks; returns this peer's payload."""
        return service.handshake(payload)

    @mcp.tool
    def receive_commit(msg: dict) -> dict:
        """Accept the opponent's sealed commitment hash for their next step."""
        return service.receive_commit(msg)

    @mcp.tool
    def receive_reveal(pub: dict) -> dict:
        """Accept the public reveal (hint, scent, barrier declaration); may return events."""
        return service.receive_reveal(pub)

    @mcp.tool
    def receive_event(envelope: dict) -> dict:
        """Accept a sealed game event (captured confession / survival claim)."""
        return service.receive_event(envelope)

    @mcp.tool
    def audit_exchange(package: dict) -> dict:
        """Accept the opponent's full sealed log; returns our audit verdict of it."""
        return service.audit_exchange(package)

    @mcp.tool
    def get_status() -> dict:
        """Local-truth snapshot (own side only) - for monitoring, never ground truth."""
        return service.status()

    @mcp.tool
    def health_check() -> dict:
        """Liveness probe."""
        return service.health()

    if bridge is not None:
        _add_reference_tools(mcp, bridge)
    return mcp


def serve_in_thread(service: PeerService, *, host: str, port: int,
                    name: str = "p2p-pursuit-peer",
                    bridge: Any = None, stateless: bool = True) -> threading.Thread:
    """Run the FastMCP HTTP server on a daemon thread; returns once started.

    ``stateless`` defaults ON, and that is an interop decision rather than a
    performance one. A stateful streamable-HTTP server requires every caller to
    complete an ``initialize`` handshake and echo the ``Mcp-Session-Id`` on each
    later request; a peer whose client posts tool calls without one gets 400 and
    never reaches our engine at all. Measured live 2026-08-02 against a real
    opponent: hundreds of `Created new transport ... -> 400 Bad Request`, three
    sub-games lost to 180 s turn timeouts, not one move exchanged.

    Nothing in either dialect needs the session. Both are request/response tool
    calls - the reference surface is explicitly fire-and-forget, with replies
    arriving as fresh calls into the *other* peer's server - so no message is
    ever pushed from server to client, which is the only thing statelessness
    costs. Accepting the superset of clients is therefore free, and in a league
    where the opponent's transport is not ours to fix, it is the difference
    between a match and a forfeit.
    """
    mcp = build_server(service, name, bridge)

    def run() -> None:
        mcp.run(transport="http", host=host, port=port, show_banner=False,
                stateless_http=stateless)

    thread = threading.Thread(target=run, name=f"mcp-server-{port}", daemon=True)
    thread.start()
    return thread


def wait_until_up(link: Any, *, attempts: int = 60, delay: float = 2.0) -> bool:
    """Retry the opponent's health tool until their server is up (start order agnostic).

    Every iteration also asks the link whether the opponent has *already reached
    us*, because that is both faster and stronger evidence than a probe of ours.
    It matters over a tunnel: each failed probe costs its whole timeout, so this
    loop can run for minutes, while a reference-derived peer gives us only ~60 s
    to answer its `negotiate` before it exits. Measured 2026-08-01 over two
    Cloudflare tunnels: both peers alive and reachable, neither able to start.
    """
    import time

    contacted = getattr(link, "opponent_already_contacted", None)
    for _ in range(attempts):
        if contacted is not None and contacted():
            return True
        try:
            if link.health(timeout=5).get("ok"):
                return True
        except Exception:  # noqa: BLE001 - any transport failure just means "not yet"
            pass
        time.sleep(delay)
    return False
