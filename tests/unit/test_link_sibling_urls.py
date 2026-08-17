"""The link survives an opponent moving between mount layouts mid-match.

gal-roy1 alternated between `/cop/mcp` + `/thief/mcp` and a bare `/mcp` seven
times in one evening, twice while we were booting. The link resolves its URL
once at startup, so every move cost a relaunch and a 90-second boot - and the
failure reads as "opponent never came up" while their other mount answers fine.
"""

from __future__ import annotations

import pytest

from p2p_pursuit.infra.mcp_client import McpLink, sibling_urls
from p2p_pursuit.infra.transport import LinkError

BASE = "http://galbb.freeddns.org:6000"


class Recording(McpLink):
    """Real candidate loop, fake transport: records the URLs it reaches for."""

    def __init__(self, url: str, dead: tuple[str, ...] = ()) -> None:
        super().__init__(url)
        self.dead, self.tried = dead, []

    def _invoke(self, url, tool, args, timeout):  # noqa: ANN001, ANN202
        self.tried.append(url)
        if any(url.endswith(d) for d in self.dead):
            raise RuntimeError("Session terminated")
        return {"ok": True, "url": url}


def test_a_role_mount_falls_back_to_the_bare_one() -> None:
    assert sibling_urls(f"{BASE}/thief/mcp") == [f"{BASE}/thief/mcp", f"{BASE}/mcp"]
    assert sibling_urls(f"{BASE}/cop/mcp") == [f"{BASE}/cop/mcp", f"{BASE}/mcp"]


def test_our_own_role_word_is_recognised_too() -> None:
    assert sibling_urls(f"{BASE}/police/mcp")[1] == f"{BASE}/mcp"


def test_an_ordinary_url_has_no_sibling() -> None:
    """A tunnel URL must not acquire a phantom alternative."""
    for url in (f"{BASE}/mcp", "https://x.trycloudflare.com/mcp", "https://x/a/b/mcp"):
        assert sibling_urls(url) == [url]


def test_the_sibling_is_used_when_the_configured_path_is_dead() -> None:
    link = Recording(f"{BASE}/thief/mcp", dead=("/thief/mcp",))
    assert link.negotiate({"a": 1})["url"] == f"{BASE}/mcp"
    assert link.tried == [f"{BASE}/thief/mcp", f"{BASE}/mcp"]


def test_the_survivor_is_promoted_so_the_dead_path_is_not_retried() -> None:
    """Otherwise every turn of the match pays for one failed request."""
    link = Recording(f"{BASE}/thief/mcp", dead=("/thief/mcp",))
    link.negotiate({"a": 1})
    link.tried.clear()
    link.negotiate({"a": 2})
    assert link.tried == [f"{BASE}/mcp"]
    assert link.url == f"{BASE}/mcp"


def test_a_healthy_link_never_touches_the_sibling() -> None:
    link = Recording(f"{BASE}/thief/mcp")
    link.negotiate({"a": 1})
    assert link.tried == [f"{BASE}/thief/mcp"]


def test_every_candidate_failing_raises_linkerror() -> None:
    link = Recording(f"{BASE}/cop/mcp", dead=("/cop/mcp", "/mcp"))
    with pytest.raises(LinkError):
        link.negotiate({"a": 1})
