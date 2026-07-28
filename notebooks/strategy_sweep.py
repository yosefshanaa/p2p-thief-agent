"""Parameter-sensitivity study (guidelines §9): reproducible strategy sweeps.

Reruns the experiments behind STRATEGY.md §6 - the police claim-threshold
sweep and the police-vs-thief outcome matrix - and writes a CSV + markdown
summary under results/analysis/ (plus PNG charts when matplotlib is
installed: ``uv sync --extra analysis``).

Run:  uv run python notebooks/strategy_sweep.py [--seeds 12] [--games 6]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from p2p_pursuit.peer.local_match import play_sub_game  # noqa: E402
from p2p_pursuit.peer.turn_engine import TurnEngine  # noqa: E402
from p2p_pursuit.shared.config import load_role  # noqa: E402
from p2p_pursuit.strategy.police_brain import PoliceBrain  # noqa: E402
from p2p_pursuit.strategy.thief_brain import ThiefBrain  # noqa: E402

BASE = Path(__file__).resolve().parent.parent


def run_matchup(police_brain_cls, thief_brain_cls, *, seeds: int, games: int,
                claim_threshold: float | None = None) -> dict:
    shared, p_cfg = load_role(BASE / "config" / "police")
    _, t_cfg = load_role(BASE / "config" / "thief")
    captures = police_pts = thief_pts = 0
    for seed in range(seeds):
        police_brain = police_brain_cls()
        if claim_threshold is not None:
            police_brain.claim_threshold = claim_threshold
        police = TurnEngine("police", shared, p_cfg, brain=police_brain, seed=seed * 2)
        thief = TurnEngine("thief", shared, t_cfg, brain=thief_brain_cls(),
                           seed=seed * 2 + 1)
        for n in range(1, games + 1):
            police.start_sub_game(n)
            thief.start_sub_game(n)
            play_sub_game(police, thief)
            captures += police.end.ending == "capture"
            p, t = police.score_table.score(police.end.ending)
            police_pts += p
            thief_pts += t
    total = seeds * games
    return {"games": total, "captures": captures, "capture_rate": captures / total,
            "police_points": police_pts, "thief_points": thief_pts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--games", type=int, default=6)
    args = parser.parse_args()
    out_dir = BASE / "results" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for threshold in (0.05, 0.10, 0.15, 0.20, 0.30):
        stats = run_matchup(PoliceBrain, ThiefBrain, seeds=args.seeds,
                            games=args.games, claim_threshold=threshold)
        rows.append({"claim_threshold": threshold, **stats})
        print(f"claim_threshold={threshold:.2f}  captures={stats['captures']:3d}"
              f"/{stats['games']}  police={stats['police_points']}"
              f"  thief={stats['thief_points']}", file=sys.stderr)

    csv_path = out_dir / "claim_threshold_sweep.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {csv_path}", file=sys.stderr)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        xs = [r["claim_threshold"] for r in rows]
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(xs, [r["capture_rate"] * 100 for r in rows], "o-", label="capture rate %")
        ax.axhline(25, color="gray", ls="--", label="points break-even (25%)")
        ax.set_xlabel("police claim threshold (belief mass at own cell)")
        ax.set_ylabel("capture rate over the sweep [%]")
        ax.set_title("Claim-threshold sensitivity - every claim leaks our position")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "claim_threshold_sweep.png", dpi=150)
        print(f"wrote {out_dir / 'claim_threshold_sweep.png'}", file=sys.stderr)
    except ImportError:
        print("matplotlib not installed (uv sync --extra analysis) - CSV only",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
