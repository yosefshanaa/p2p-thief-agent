"""Peer link abstraction: how one peer invokes the opponent's tools.

DirectLink wires two in-process services (tests, sim); McpLink (mcp_client)
speaks real FastMCP over HTTP. Both expose the same method surface, so the
runner never changes between loopback and the public internet.
"""

from __future__ import annotations

from typing import Any


class LinkError(RuntimeError):
    pass


class DirectLink:
    """In-process opponent: calls the other peer's service directly."""

    def __init__(self, opponent_service: Any) -> None:
        self._svc = opponent_service

    def handshake(self, payload: dict, timeout: float | None = None) -> dict:
        return self._svc.handshake(payload)

    def commit(self, msg: dict, timeout: float | None = None) -> dict:
        return self._svc.receive_commit(msg)

    def reveal(self, pub: dict, timeout: float | None = None) -> dict:
        return self._svc.receive_reveal(pub)

    def event(self, envelope: dict, timeout: float | None = None) -> dict:
        return self._svc.receive_event(envelope)

    def audit(self, package: dict, timeout: float | None = None) -> dict:
        return self._svc.audit_exchange(package)

    def health(self, timeout: float | None = None) -> dict:
        return self._svc.health()
