"""Command-line entry points: peer | sim | replay | verify | smoke | learn |
authorize.

Thin argument-parsing shell: every operation is delegated to the PursuitSDK
facade (guidelines ch. 4 - no business logic outside the SDK) by the handlers
in :mod:`.commands`. stdout carries machine-readable JSON only; human logs go
to stderr.
"""

from __future__ import annotations

import argparse

from .commands import (
    cmd_authorize,
    cmd_peer,
    cmd_replay,
    cmd_sim,
    cmd_smoke,
    cmd_verify,
)
from .domain.rules import POLICE, THIEF


def main(argv: list[str] | None = None) -> int:
    from .shared.env import load_dotenv
    from .shared.logging_setup import configure

    configure()
    load_dotenv()  # git-ignored local secrets; exported vars always win
    parser = argparse.ArgumentParser(prog="p2p-pursuit")
    sub = parser.add_subparsers(dest="command", required=True)

    peer = sub.add_parser("peer", help="run one autonomous peer over the network")
    peer.add_argument("--role", choices=[POLICE, THIEF], default=None,
                      help="defaults to this repo's ROLE marker if present")
    peer.add_argument("--config-dir", default=None)
    peer.add_argument("--no-gui", action="store_true")
    peer.add_argument("--seed", type=int, default=None)
    peer.add_argument("--out", default="results")
    peer.add_argument("--counted", action="store_true",
                      help="a counted league match (enforces 6 sub-games)")
    peer.add_argument("--prior-counted", type=int, default=0,
                      help="truthful count of prior counted games (rule #37)")
    peer.add_argument("--games", type=int, default=None)
    peer.set_defaults(fn=cmd_peer)

    sim = sub.add_parser("sim", help="in-process series (tactics lab / demo)")
    sim.add_argument("--games", type=int, default=None)
    sim.add_argument("--seed", type=int, default=None)
    sim.add_argument("--out", default="results")
    sim.set_defaults(fn=cmd_sim)

    replay = sub.add_parser("replay", help="verify + view a sealed sub-game log")
    replay.add_argument("--log", required=True)
    replay.add_argument("--no-gui", action="store_true")
    replay.set_defaults(fn=cmd_replay)

    verify = sub.add_parser(
        "verify", help="re-check a played match: every commitment sent in play "
                       "must be revealed as the same (payload, nonce)")
    verify.add_argument("--dir", required=True, help="a match output directory")
    verify.set_defaults(fn=cmd_verify)

    smoke = sub.add_parser("smoke", help="probe a peer's MCP endpoint")
    smoke.add_argument("url")
    smoke.set_defaults(fn=cmd_smoke)

    from .learn.cli import add_parser as add_learn_parser

    add_learn_parser(sub)

    auth = sub.add_parser("authorize", help="one-time Gmail OAuth consent (writes token.json)")
    auth.add_argument("--credentials", default="credentials.json")
    auth.add_argument("--token", default="token.json")
    auth.set_defaults(fn=cmd_authorize)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
