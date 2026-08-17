"""One endpoint per role: `{role}` in the opponent URL, retargeted per sub-game.

gal-roy1 serves `/cop/mcp` and `/thief/mcp` on one port and mounts nothing at
`/mcp`. Under alternation the agent we must push to changes every sub-game, and
getting it wrong is silent in exactly the way that matters: sub-game 1 plays
perfectly and every even one talks to an agent that is not playing.
"""

from __future__ import annotations

from types import SimpleNamespace

from p2p_pursuit.domain.rules import POLICE, THIEF
from p2p_pursuit.peer.series_protocol import retarget_link, role_for, take_role
from p2p_pursuit.shared.config import opponent_url_for

TEMPLATE = "http://galbb.freeddns.org:6000/{role}/mcp"


def _rt(template: str, *, natural: str = POLICE, alternate: bool = True) -> SimpleNamespace:
    link = SimpleNamespace(url=opponent_url_for(template, THIEF))
    return SimpleNamespace(
        peer=SimpleNamespace(opponent_url=template, alternate_roles=alternate),
        # the reference dialect wraps the real link in the bridge
        link=SimpleNamespace(link=link),
        engine=SimpleNamespace(role=natural, set_role=lambda r: None),
        service=SimpleNamespace(my_handshake={"role": natural}),
        natural_role=natural,
    )


def test_substitution_uses_their_vocabulary_not_ours() -> None:
    """Our `police` is their `cop`; asking for /police/mcp gets a 404."""
    assert opponent_url_for(TEMPLATE, THIEF).endswith("/thief/mcp")
    assert opponent_url_for(TEMPLATE, POLICE).endswith("/cop/mcp")
    assert "police" not in opponent_url_for(TEMPLATE, POLICE)


def test_a_url_without_the_placeholder_is_untouched() -> None:
    """Every other opponent we have played serves one endpoint for both roles."""
    plain = "https://x.trycloudflare.com/mcp"
    assert opponent_url_for(plain, THIEF) == plain


def test_retarget_follows_the_role_we_just_took() -> None:
    rt = _rt(TEMPLATE)
    retarget_link(rt, THIEF, lambda _m: None)
    assert rt.link.link.url.endswith("/cop/mcp")  # we are thief, so they cop
    retarget_link(rt, POLICE, lambda _m: None)
    assert rt.link.link.url.endswith("/thief/mcp")


def test_retarget_is_a_no_op_without_a_placeholder() -> None:
    rt = _rt("https://x.trycloudflare.com/mcp")
    rt.link.link.url = "https://x.trycloudflare.com/mcp"
    retarget_link(rt, THIEF, lambda _m: None)
    assert rt.link.link.url == "https://x.trycloudflare.com/mcp"


def test_a_six_sub_game_series_alternates_endpoints() -> None:
    """The whole point: police on 1/3/5 pushes to their thief, and back again."""
    rt = _rt(TEMPLATE)
    seen = []
    for n in range(1, 7):
        rt.engine.role = role_for(rt.natural_role, n)  # set_role is a stub here
        take_role(rt, n, lambda _m: None)
        seen.append(rt.link.link.url.rsplit("/", 2)[1])
    assert seen == ["thief", "cop", "thief", "cop", "thief", "cop"]


def test_a_fixed_role_series_never_moves_the_endpoint() -> None:
    rt = _rt(TEMPLATE, alternate=False)
    for n in range(1, 7):
        take_role(rt, n, lambda _m: None)
    assert rt.link.link.url.endswith("/thief/mcp")


def test_an_unwrapped_link_is_retargeted_too() -> None:
    """Native dialect: `rt.link` IS the link, with no bridge around it."""
    rt = _rt(TEMPLATE)
    rt.link = SimpleNamespace(url=opponent_url_for(TEMPLATE, THIEF))
    retarget_link(rt, THIEF, lambda _m: None)
    assert rt.link.url.endswith("/cop/mcp")
