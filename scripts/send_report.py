#!/usr/bin/env python3
"""Mail an already-filed result - the recovery path when a run never reached
`cli.py`'s report step.

    scripts/send_report.py results/thief-ahk-yosi-vs-saedshki-.../result_*.json \
        --to someone@example.com [--mode send|draft] [--role thief]

The sealed artifacts under results/ are the record; the email is only a copy of
them (#35, both teams send separately). So a series that played correctly but
died before delivery - a GUI left open, a Ctrl-C, a closed laptop - needs a way
to send that copy without replaying the match. This is that way.

It reuses the runtime's own delivery path rather than reimplementing it: the
same Gatekeeper limits, the same transport picker, the same envelope builder.
A dry-run mode prints what would be sent instead of sending it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

# Re-exec under the venv interpreter if we were started by some other python.
# The Gmail client lives only in the venv, and `pick_email_transport` swallows
# an ImportError into the dry-run transport - so the wrong interpreter does not
# fail loudly, it silently "delivers" nothing. Fix the cause, not the symptom.
_VENV_PY = REPO / ".venv" / "bin" / "python"
if _VENV_PY.is_file() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import os

    os.execv(str(_VENV_PY), [str(_VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("result", type=Path, help="path to a filed result_<game_id>.json")
    ap.add_argument("--to", help="recipient; defaults to the role config's own recipient")
    ap.add_argument("--mode", choices=("send", "draft"), default=None,
                    help="defaults to the role config's own mode")
    ap.add_argument("--role", choices=("police", "thief"), default="thief",
                    help="which config/<role> supplies the rate limits and defaults")
    args = ap.parse_args()

    if not args.result.is_file():
        print(f"no such result file: {args.result}", file=sys.stderr)
        return 2

    from p2p_pursuit.infra.email_sender import send_report
    from p2p_pursuit.sdk import PursuitSDK
    from p2p_pursuit.shared.config import load_rate_limits, load_role
    from p2p_pursuit.shared.gatekeeper import Gatekeeper

    config_dir = REPO / "config" / args.role
    shared, peer = load_role(config_dir)
    to_addr = args.to or peer.email_recipient
    mode = args.mode or peer.email_mode

    result = json.loads(args.result.read_text(encoding="utf-8"))
    game_id = result.get("game_id", args.result.stem)

    # The lecturer's address is the one mistake this script must not make by
    # accident, so it is stated out loud before anything is sent.
    print(f"  result   {args.result}")
    print(f"  game_id  {game_id}")
    print(f"  to       {to_addr}")
    print(f"  mode     {mode}")

    local = load_rate_limits(config_dir)
    gate = Gatekeeper.from_config({**local, **shared.rate_limiter},
                                  daily_quota=local.get("daily_quota", 50))
    transport = PursuitSDK().pick_email_transport(mode, notify=lambda m: print(f"  {m}"))
    receipt = send_report(transport=transport, gatekeeper=gate, to_addr=to_addr,
                          subject=f"[p2p-pursuit] result {game_id}",
                          attachments={f"result_{game_id}.json": result}, mode=mode)
    print(f"[email] {receipt}")
    # `delivered: True` is not the same as "a mail server accepted it": the
    # dry-run transport reports success too, and its id is literally "dry-run-N".
    # Treat that as failure in `send` mode so a silent non-delivery cannot pass
    # for a sent report.
    rid = str((receipt.get("receipt") or {}).get("id", ""))
    if mode == "send" and rid.startswith("dry-run"):
        print("[email] NOT ACTUALLY SENT - dry-run transport stood in for Gmail.\n"
              "        Check credentials.json/token.json, or run:\n"
              "        PYTHONPATH=src .venv/bin/p2p-pursuit authorize", file=sys.stderr)
        return 1
    return 0 if receipt.get("delivered") else 1


if __name__ == "__main__":
    raise SystemExit(main())
