"""Command-line entry points: peer | sim | replay | smoke | learn | authorize.

Thin argument-parsing shell: every operation is delegated to the PursuitSDK
facade (guidelines ch. 4 - no business logic outside the SDK). stdout
carries machine-readable JSON only; human logs go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from .domain.rules import POLICE, THIEF
from .sdk import PursuitSDK


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def cmd_peer(args: argparse.Namespace) -> int:
    from .shared.config import repo_default_role

    role = args.role or repo_default_role()
    if role is None:
        _err("peer: --role required (this checkout has no ROLE marker)")
        return 2
    args.role = role
    sdk = PursuitSDK()
    runtime = sdk.create_peer(args.role, Path(args.config_dir) if args.config_dir else None,
                              out_dir=Path(args.out), seed=args.seed, counted=args.counted,
                              prior_counted_games=args.prior_counted, num_games=args.games)
    # Sub-game 1 is played in our natural role, so the first endpoint we push to
    # is the one holding the other one. `opponent_url_for` is a no-op unless the
    # URL carries `{role}`, and `series_protocol.take_role` re-targets it at
    # every alternation boundary.
    from .shared.config import opponent_url_for

    their_role = THIEF if role == POLICE else POLICE
    runtime.attach(sdk.make_link(opponent_url_for(
        runtime.peer.opponent_url, their_role, runtime.peer.opponent_doors)))
    runtime.start_server()
    if not runtime.connect():
        return 2
    result_holder: dict = {}

    def play() -> None:
        result_holder["result"] = runtime.run_series()

    worker = threading.Thread(target=play, name="series", daemon=True)
    worker.start()
    if not args.no_gui:
        try:
            from .gui.live_view import LiveView

            LiveView(runtime.service.status, f"p2p-pursuit - {args.role}",
                     args.role).run()
        except Exception as exc:  # noqa: BLE001 - no display etc.
            _err(f"[gui] disabled ({exc}); running headless")
    worker.join()
    result = result_holder.get("result", {})
    transport = sdk.pick_email_transport(runtime.peer.email_mode, notify=_err)
    receipt = runtime.report(result, transport)
    _err(f"[email] {receipt}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_sim(args: argparse.Namespace) -> int:
    from .domain.game_ids import make_game_id, new_game_uid
    from .report import artifacts, sim_artifacts
    from .shared.config import load_role

    sdk = PursuitSDK()
    game_uid, game_id = new_game_uid(), make_game_id("police-sim", "thief-sim")
    out = Path(args.out) / f"sim-{game_id}"
    rows: list[dict] = []
    loaded_shared, _ = load_role(Path("config/police"))
    per_sub_game = sim_artifacts.sub_game_writer(
        out=out, game_uid=game_uid, game_id=game_id, shared=loaded_shared,
        rows=rows, log_fn=_err)
    shared, police_cfg, _thief_cfg, series = sdk.run_local_series(
        num_games=args.games, seed=args.seed, on_sub_game=per_sub_game)
    result = sdk.build_local_result(
        game_uid=game_uid, game_id=game_id, shared=shared, police_cfg=police_cfg,
        sub_games=rows, police_total=series.police_total,
        thief_total=series.thief_total, tokens_used=series.tokens_used)
    artifacts.write_result(out, game_id, result)
    _err(f"[sim] totals police={series.police_total} thief={series.thief_total} "
         f"winner={series.series_winner}; artifacts in {out}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    sdk = PursuitSDK()
    path = Path(args.log)
    view = sdk.load_replay(path)
    if args.no_gui:
        for item in view["timeline"]:
            stamp = "Verified OK" if item["verified"] else "TAMPERED"
            barrier = f" barrier={item['barrier']}" if item["barrier"] else ""
            _err(f"{item['role']:6s} step {item['step']:2d} -> {item['pos_after']}"
                 f"{barrier}  [{stamp}]  {item['hint'][:44]}")
        print(json.dumps({"log": str(path), "verdict": view["verdict"],
                          "records_checked": view["records_checked"]}))
        return 0 if view["verdict"] == "Verified OK" else 3
    from .gui.replay_view import ReplayView

    ReplayView(path).run()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-check a played match's sealed logs: does every commitment bind?"""
    report = PursuitSDK().audit_binding(Path(args.dir))
    for row in report["sub_games"]:
        mine = "OK " if row["mine_binds"] else "FAIL"
        theirs = ("OK " if row["theirs_binds"] else "FAIL") \
            if row["their_reveal_received"] else "none"
        _err(f"  g{row['sub_game']:02d} {row['role']:6s} "
             f"{row['records']:3d} records / {row['commitments_sent']:3d} sent  "
             f"ours={mine}  theirs={theirs}")
        for violation in row["mine_violations"] + row["theirs_violations"]:
            _err(f"        {violation}")
    _err(f"[verify] our reveal binds: {report['mine_binds']}; "
         f"theirs: {report['theirs_binds']} ({report['reveals_received']} received)")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["mine_binds"] and report["theirs_binds"] else 3


def cmd_smoke(args: argparse.Namespace) -> int:
    probe = PursuitSDK().smoke(args.url)
    if probe["reachable"]:
        _err(f"[smoke] dialect={probe['dialect']}: {probe['guidance']}")
    else:
        _err(f"[smoke] unreachable: {probe['error']}")
    print(json.dumps({"url": args.url, **probe}))
    return 0 if probe["reachable"] else 4


def cmd_authorize(args: argparse.Namespace) -> int:
    _err(PursuitSDK().authorize_gmail(Path(args.credentials), Path(args.token)))
    return 0


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
