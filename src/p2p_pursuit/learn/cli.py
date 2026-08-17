"""``p2p-pursuit learn`` - tune the doctrine offline, clone a played opponent.

Both commands write JSON to stdout and progress to stderr, like the rest of the
CLI. Neither is ever invoked during a match: ``tune`` produces a file that a
human commits, and that committed file is what a counted match plays.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..domain.rules import POLICE, THIEF
from ..strategy import params
from ..strategy.params import Doctrine
from . import arena, cem, population
from .clone_data import samples_from_match
from .clone_fit import agreement, fit_by_role


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _report(label: str, result: arena.Score) -> dict:
    _err(f"[learn] {label}: {result.points:.3f} pts/sub-game  "
         f"capture {result.capture_rate:.0%}  survival {result.survival_rate:.0%}")
    return {"points": round(result.points, 4),
            "capture_rate": round(result.capture_rate, 4),
            "survival_rate": round(result.survival_rate, 4),
            "per_opponent": {k: round(v, 3) for k, v in result.per_opponent.items()}}


def cmd_tune(args: argparse.Namespace) -> int:
    names = tuple(args.opponents.split(",")) if args.opponents else tuple(population.build())
    pool = population.build(names)
    roles = (POLICE, THIEF) if args.role is None else (args.role,)
    keys = params.keys_for(args.role)
    train = tuple(range(args.seed, args.seed + args.seeds))
    holdout = tuple(range(args.holdout, args.holdout + args.seeds))
    base = params.active(Path(args.out)) if Path(args.out).exists() else Doctrine()
    # Count the opponents that will actually be played: an archetype distinct
    # only as a thief contributes nothing to a thief-only search.
    facing = {n for n, m in pool.items() if set(m.roles) & {THIEF if r == POLICE else POLICE
                                                            for r in roles}}
    _err(f"[learn] {len(keys)} keys, {len(facing)} opponents, {args.seeds} seeds, "
         f"{args.generations}x{args.population} candidates on {args.workers} workers")

    with ProcessPoolExecutor(max_workers=args.workers) as workers:
        def evaluate(candidates: list[Doctrine]) -> list[float]:
            return list(workers.map(arena.points_for,
                                    [(c, names, train, roles) for c in candidates]))

        tuned, run = cem.search_doctrine(
            base, keys, evaluate, generations=args.generations,
            population=args.population, seed=args.seed)

    before = arena.score(base, pool, holdout, roles=roles)
    after = arena.score(tuned, pool, holdout, roles=roles)
    improved = after.points > before.points
    # The hold-out decides. A gain on the seeds the search optimised is the
    # search reporting its own noise back to us; only unseen seeds are evidence.
    if improved or args.force:
        params.save(tuned, Path(args.out))
        forced = "" if improved else " (forced: the hold-out did NOT improve)"
        _err(f"[learn] wrote {args.out}{forced}")
    else:
        _err("[learn] hold-out did not improve - keeping the shipped doctrine")
    print(json.dumps({
        "keys": list(keys), "opponents": list(names),
        "train_seeds": [train[0], train[-1]], "holdout_seeds": [holdout[0], holdout[-1]],
        "train": {"baseline": round(run.baseline, 4), "best": round(run.best_score, 4),
                  "history": [vars(s) for s in run.history]},
        "holdout": {"baseline": _report("hold-out baseline", before),
                    "tuned": _report("hold-out tuned", after)},
        "accepted": bool(improved or args.force), "written_to": args.out,
        "doctrine": json.loads(json.dumps(vars(tuned))),
    }, indent=2))
    return 0


def cmd_clone(args: argparse.Namespace) -> int:
    match = Path(args.match)
    samples = samples_from_match(match)
    name = args.name or match.name
    if len(samples) < args.min_samples:
        _err(f"[learn] {len(samples)} decisions in {match} - below --min-samples "
             f"{args.min_samples}; a clone fitted on this would be noise")
        return 3
    weights = fit_by_role(samples)
    scores = {role: round(agreement(w, [s for s in samples if s.role == role]), 4)
              for role, w in weights.items()}
    out = Path(args.out) / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"team": name, "source": str(match), "samples": len(samples),
               "agreement": scores, "weights": weights}
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for role, value in scores.items():
        _err(f"[learn] {name} as {role}: {value:.0%} of moves reproduced")
    _err(f"[learn] wrote {out}; it joins the pool as clone:{name}")
    print(json.dumps(payload, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    """Build a decision table for one team from every match we played them in."""
    from .recorded import agreement as recorded_agreement
    from .recorded import table_from_samples

    samples: list = []
    for directory in args.match:
        samples.extend(samples_from_match(Path(directory)))
    if len(samples) < args.min_samples:
        _err(f"[learn] {len(samples)} decisions across {len(args.match)} directories - "
             f"below --min-samples {args.min_samples}")
        return 3
    table = table_from_samples(samples)
    # Hold out every fourth decision and rebuild without it. A table that
    # reproduces its own training rows is a dictionary, not a model; what the
    # pool needs to know is how it answers ground it has not stood on.
    held = [s for i, s in enumerate(samples) if i % 4 == 0]
    trained = table_from_samples([s for i, s in enumerate(samples) if i % 4])
    scores = {role: round(recorded_agreement(trained.get(role, []),
                                             [s for s in held if s.role == role]), 4)
              for role in table}
    out = Path(args.out) / "recorded" / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"team": args.name, "sources": list(args.match), "samples": len(samples),
               "states": {role: len(rows) for role, rows in table.items()},
               "holdout_agreement": scores, "roles": table}
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    for role, value in scores.items():
        _err(f"[learn] {args.name} as {role}: {len(table[role])} states, "
             f"{value:.0%} of held-out moves reproduced")
    _err(f"[learn] wrote {out}; it joins the pool as recorded:{args.name}")
    print(json.dumps({k: v for k, v in payload.items() if k != "roles"}, indent=2))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Print what the played matches say about our own play. Never writes."""
    from .review import format_review, review

    result = review(Path(args.matches))
    if not result.sub_games:
        _err(f"[learn] no sealed sub-game logs under {args.matches}")
        return 3
    _err(format_review(result))
    print(json.dumps(result.as_dict(), indent=2))
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    learn = sub.add_parser("learn", help="offline policy search and opponent cloning")
    inner = learn.add_subparsers(dest="learn_command", required=True)

    tune = inner.add_parser("tune", help="CEM over the doctrine vector")
    tune.add_argument("--role", choices=[POLICE, THIEF], default=None,
                      help="search only one role's keys (default: both)")
    tune.add_argument("--opponents", default=None, help="comma-separated pool names")
    tune.add_argument("--generations", type=int, default=8)
    tune.add_argument("--population", type=int, default=24)
    tune.add_argument("--seeds", type=int, default=12, help="seeds per candidate")
    tune.add_argument("--seed", type=int, default=7000, help="first training seed")
    tune.add_argument("--holdout", type=int, default=9000, help="first hold-out seed")
    tune.add_argument("--workers", type=int, default=4)
    tune.add_argument("--out", default=str(params.DEFAULT_PATH))
    tune.add_argument("--force", action="store_true",
                      help="write even if the hold-out did not improve")
    tune.set_defaults(fn=cmd_tune)

    clone = inner.add_parser("clone", help="fit an opponent policy to a played match")
    clone.add_argument("--match", required=True, help="directory of sealed logs")
    clone.add_argument("--name", default=None, help="team name (default: directory name)")
    clone.add_argument("--min-samples", type=int, default=30)
    clone.add_argument("--out", default=str(population.CLONE_DIR))
    clone.set_defaults(fn=cmd_clone)

    record = inner.add_parser(
        "record", help="build a decision table for a team from its played matches")
    record.add_argument("--match", required=True, action="append",
                        help="a directory of sealed logs (repeat for every series)")
    record.add_argument("--name", required=True, help="team name")
    record.add_argument("--min-samples", type=int, default=60)
    record.add_argument("--out", default=str(population.CLONE_DIR))
    record.set_defaults(fn=cmd_record)

    review = inner.add_parser(
        "review", help="read the played archive back as evidence (read-only)")
    review.add_argument("--matches", default="matches",
                        help="root directory of sealed match logs")
    review.set_defaults(fn=cmd_review)
