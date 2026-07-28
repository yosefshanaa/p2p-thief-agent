"""Command-line entry points: peer | sim | replay | smoke | authorize.

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
    runtime.start_server()
    if not runtime.connect(sdk.make_link(runtime.peer.opponent_url)):
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
    from .peer import log_manager
    from .report import artifacts, results
    from .shared import sysinfo

    sdk = PursuitSDK()
    game_uid, game_id = new_game_uid(), make_game_id("police-sim", "thief-sim")
    out = Path(args.out) / f"sim-{game_id}"
    rows: list[dict] = []
    shared_holder: dict = {}

    def per_sub_game(police, thief, outcome) -> None:
        audit = {"mine_of_them": outcome.audit_of_thief,
                 "theirs_of_us": outcome.audit_of_police}
        log = log_manager.build_log(police, thief.my_records, game_uid=game_uid,
                                    game_id=game_id, audit=audit)
        log_manager.write_log(log, out)
        artifacts.write_config_copy(out, game_id, outcome.index,
                                    shared_holder["shared"].raw, game_uid)
        rows.append(results.sub_game_row(
            index=outcome.index, ending=outcome.ending, winner=outcome.winner,
            cause=outcome.cause, police_score=outcome.police_score,
            thief_score=outcome.thief_score, moves_played=outcome.thief_steps,
            github_commit=sysinfo.git_commit(),
            audit_verdict=outcome.audit_of_thief["verdict"]))
        _err(f"[sim] g{outcome.index}: {outcome.ending} winner={outcome.winner} "
             f"({outcome.cause})")

    from .shared.config import load_role

    shared_holder["shared"], _ = load_role(Path("config/police"))
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


def cmd_smoke(args: argparse.Namespace) -> int:
    health = PursuitSDK().smoke(args.url)
    print(json.dumps({"url": args.url, "health": health}))
    return 0 if health.get("ok") else 4


def cmd_authorize(args: argparse.Namespace) -> int:
    _err(PursuitSDK().authorize_gmail(Path(args.credentials), Path(args.token)))
    return 0


def main(argv: list[str] | None = None) -> int:
    from .shared.logging_setup import configure

    configure()
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

    smoke = sub.add_parser("smoke", help="probe a peer's MCP endpoint")
    smoke.add_argument("url")
    smoke.set_defaults(fn=cmd_smoke)

    auth = sub.add_parser("authorize", help="one-time Gmail OAuth consent (writes token.json)")
    auth.add_argument("--credentials", default="credentials.json")
    auth.add_argument("--token", default="token.json")
    auth.set_defaults(fn=cmd_authorize)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
