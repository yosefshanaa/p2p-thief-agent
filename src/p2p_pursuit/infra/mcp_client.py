"""FastMCP client link: invoking the opponent's tools over HTTP.

Same surface as transport.DirectLink, so the series runner is identical on
loopback and over a tunnel. Every call carries an explicit timeout for the
Deadline Tracker to enforce.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .transport import LinkError


class McpLink:
    def __init__(self, url: str) -> None:
        self.url = url

    def _call(self, tool: str, args: dict[str, Any], timeout: float | None) -> dict:
        from fastmcp import Client

        async def go() -> dict:
            async with Client(self.url, timeout=timeout) as client:
                result = await client.call_tool(tool, args, timeout=timeout)
                if getattr(result, "data", None) is not None:
                    return result.data
                for block in getattr(result, "content", []) or []:
                    text = getattr(block, "text", None)
                    if text:
                        return json.loads(text)
                raise LinkError(f"{tool}: empty result")

        try:
            return asyncio.run(go())
        except LinkError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize transport failures
            raise LinkError(f"{tool} failed against {self.url}: {exc}") from exc

    def list_tools(self, timeout: float | None = None) -> list[str]:
        """Names of the tools the opponent advertises - how we classify their dialect."""
        from fastmcp import Client

        async def go() -> list[str]:
            async with Client(self.url, timeout=timeout) as client:
                return [tool.name for tool in await client.list_tools()]

        try:
            return asyncio.run(go())
        except Exception as exc:  # noqa: BLE001 - normalize transport failures
            raise LinkError(f"list_tools failed against {self.url}: {exc}") from exc

    def handshake(self, payload: dict, timeout: float | None = None) -> dict:
        return self._call("handshake", {"payload": payload}, timeout)

    def commit(self, msg: dict, timeout: float | None = None) -> dict:
        return self._call("receive_commit", {"msg": msg}, timeout)

    def reveal(self, pub: dict, timeout: float | None = None) -> dict:
        return self._call("receive_reveal", {"pub": pub}, timeout)

    def event(self, envelope: dict, timeout: float | None = None) -> dict:
        return self._call("receive_event", {"envelope": envelope}, timeout)

    def audit(self, package: dict, timeout: float | None = None) -> dict:
        return self._call("audit_exchange", {"package": package}, timeout)

    # -- reference dialect: fire-and-forget pushes, replies arrive at our server --
    def negotiate(self, signed: dict, timeout: float | None = None) -> dict:
        return self._call("negotiate", {"message": signed}, timeout)

    def receive_turn(self, message: dict, timeout: float | None = None) -> dict:
        return self._call("receive_turn", {"message": message}, timeout)

    def submit_audit(self, payload: dict, timeout: float | None = None) -> dict:
        return self._call("submit_audit", {"payload": payload}, timeout)

    def health(self, timeout: float | None = None) -> dict:
        return self._call("health_check", {}, timeout)

    def status(self, timeout: float | None = None) -> dict:
        return self._call("get_status", {}, timeout)
