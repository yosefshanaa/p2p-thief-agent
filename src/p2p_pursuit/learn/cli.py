"""``p2p-pursuit learn`` - tune the doctrine offline, clone a played opponent.

This module is the argparse surface only; the handlers live in :mod:`.commands`.
Neither command is ever invoked during a match: ``tune`` produces a file that a
human commits, and that committed file is what a counted match plays.
"""

from __future__ import annotations

import argparse

from ..domain.rules import POLICE, THIEF
from ..strategy import params
from . import population
from .commands import cmd_clone, cmd_record, cmd_review, cmd_tune


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
