"""The two offline commands added with v8 have to be reachable and read-only.

`learn review` reads the sealed archive and prints what it says about our own
play; `learn record` turns a team's decisions into a sparring partner. Both are
offline-only by construction - `learn` is never invoked during a match - but
`review` in particular is pointed straight at five counted matches' audit trail,
so "it does not write" is a property worth asserting rather than assuming.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from p2p_pursuit.cli import main

MATCHES = Path("matches")


def digest(root: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            sha.update(path.read_bytes())
    return sha.hexdigest()


def test_review_is_wired_and_reports(capsys):
    assert main(["learn", "review", "--matches", str(MATCHES)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sub_games"] >= 80
    assert payload["inverse_right"] == payload["fixes"]
    assert payload["argmax_right"] < payload["fixes"] // 4


def test_review_does_not_write_a_byte_of_the_archive():
    before = digest(MATCHES)
    main(["learn", "review", "--matches", str(MATCHES)])
    assert digest(MATCHES) == before


def test_review_on_an_empty_directory_says_so_rather_than_inventing_a_report(tmp_path):
    assert main(["learn", "review", "--matches", str(tmp_path)]) == 3


def test_record_builds_a_partner_and_reports_held_out_agreement(tmp_path, capsys):
    code = main(["learn", "record", "--name", "probe", "--out", str(tmp_path),
                 "--match", "matches/gal-roy1-counted"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["samples"] > 60
    assert set(summary["holdout_agreement"]) <= {"police", "thief"}
    written = json.loads((tmp_path / "recorded" / "probe.json").read_text(encoding="utf-8"))
    assert written["roles"], "a partner with no decisions is not a partner"


def test_record_refuses_a_match_too_thin_to_learn_from(tmp_path):
    assert main(["learn", "record", "--name", "thin", "--out", str(tmp_path),
                 "--match", "matches/gal-roy1-counted", "--min-samples", "100000"]) == 3
    assert not (tmp_path / "recorded").exists()


@pytest.mark.parametrize("command", ["tune", "clone", "record", "review"])
def test_every_learn_subcommand_is_reachable(command):
    with pytest.raises(SystemExit):
        main(["learn", command, "--help"])
