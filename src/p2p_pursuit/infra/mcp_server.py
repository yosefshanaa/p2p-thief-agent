"""FastMCP server: the tools this peer exposes to its opponent (book ch. 2).

Each agent is simultaneously a server (these tools) and a client
(mcp_client.McpLink). Binds 0.0.0.0 so a tunnel can expose it publicly.
"""

from __future__ import annotations

import threading
from typing import Any

from ..peer.service import PeerService


def build_server(service: PeerService, name: str = "p2p-pursuit-peer"):
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

    return mcp


def serve_in_thread(service: PeerService, *, host: str, port: int,
                    name: str = "p2p-pursuit-peer") -> threading.Thread:
    """Run the FastMCP HTTP server on a daemon thread; returns once started."""
    mcp = build_server(service, name)

    def run() -> None:
        mcp.run(transport="http", host=host, port=port, show_banner=False)

    thread = threading.Thread(target=run, name=f"mcp-server-{port}", daemon=True)
    thread.start()
    return thread


def wait_until_up(link: Any, *, attempts: int = 60, delay: float = 2.0) -> bool:
    """Retry the opponent's health tool until their server is up (start order agnostic)."""
    import time

    for _ in range(attempts):
        try:
            if link.health(timeout=5).get("ok"):
                return True
        except Exception:  # noqa: BLE001 - any transport failure just means "not yet"
            pass
        time.sleep(delay)
    return False
