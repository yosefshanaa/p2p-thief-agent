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

#: A peer that serves one agent per role mounts `/cop/mcp` and `/thief/mcp`; one
#: that routes internally mounts a bare `/mcp`. gal-roy1 moved between those two
#: layouts seven times in one evening, twice while we were mid-boot, and each
#: move cost a full relaunch because the link resolves its URL once at startup.
#: Trying the sibling layout costs one failed request and makes us immune.
ROLE_SEGMENTS = ("cop", "thief", "police")


def sibling_urls(url: str) -> list[str]:
    """``url`` first, then the same endpoint under the other mount layout."""
    head, sep, tail = url.rstrip("/").rpartition("/")
    if not sep:
        return [url]
    parent, _, segment = head.rpartition("/")
    if segment in ROLE_SEGMENTS:          # /cop/mcp -> /mcp
        return [url, f"{parent}/{tail}"]
    return [url]


class McpLink:
    def __init__(self, url: str) -> None:
        self.url = url
        #: Ordered candidates. The one that answers is promoted, so a healthy
        #: link pays nothing for this after the first call.
        self.candidates = sibling_urls(url)

    def _promote(self, url: str) -> None:
        self.url = url
        self.candidates = [url] + [u for u in self.candidates if u != url]

    def _invoke(self, url: str, tool: str, args: dict[str, Any],
                timeout: float | None) -> dict:
        """One tool call against one URL. The only place the transport lives."""
        from fastmcp import Client

        async def go() -> dict:
            async with Client(url, timeout=timeout) as client:
                result = await client.call_tool(tool, args, timeout=timeout)
                if getattr(result, "data", None) is not None:
                    return result.data
                for block in getattr(result, "content", []) or []:
                    text = getattr(block, "text", None)
                    if text:
                        return json.loads(text)
                raise LinkError(f"{tool}: empty result")

        return asyncio.run(go())

    def _try_candidates(self, what: str, attempt: Any) -> Any:
        """Run ``attempt(url)`` over the candidates, promoting the one that works."""
        failure: Exception | None = None
        for url in list(self.candidates):
            try:
                answer = attempt(url)
            except LinkError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize transport failures
                failure = exc
                continue
            self._promote(url)
            return answer
        raise LinkError(f"{what} failed against {self.url}: {failure}") from failure

    def _call(self, tool: str, args: dict[str, Any], timeout: float | None) -> dict:
        return self._try_candidates(
            tool, lambda url: self._invoke(url, tool, args, timeout))

    def list_tools(self, timeout: float | None = None) -> list[str]:
        """Names of the tools the opponent advertises - how we classify their dialect."""
        from fastmcp import Client

        def once(url: str) -> list[str]:
            async def go() -> list[str]:
                async with Client(url, timeout=timeout) as client:
                    return [tool.name for tool in await client.list_tools()]

            return asyncio.run(go())

        # Candidate-aware for the same reason `_call` is: this is what
        # `wait_until_up` probes with, so pinning it to a moved path reports the
        # opponent as dead while their other mount is answering.
        return self._try_candidates("list_tools", once)

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
