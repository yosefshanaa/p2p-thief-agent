"""The evidence behind v6, kept runnable rather than quoted.

Every number in the brains' docstrings and in docs/STRATEGY.md §10 comes out of
`p2p-pursuit learn review`, which reads ``matches/`` and nothing else. These
tests pin the findings that motivated each change, so a claim cannot quietly
stop being true - and they assert the tool is read-only, because the sealed
archive is the audit trail for five counted matches.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from p2p_pursuit.learn.counterfactual import replay, served_fields
from p2p_pursuit.learn.review import (
    _cut_of,
    _model_of,
    _our_steps,
    death_corner_share,
    format_review,
    review,
)
from p2p_pursuit.strategy.params import active

MATCHES = Path("matches")


@pytest.fixture(scope="module")
def archive():
    return review(MATCHES)


def test_the_archive_is_still_all_there(archive):
    assert archive.sub_games >= 80, f"only {archive.sub_games} sealed sub-games found"
    assert archive.police_sub_games and archive.thief_sub_games


def test_reviewing_does_not_touch_a_single_byte_of_it():
    """The logs are five counted matches' audit trail; reading is all we may do."""
    before = _digest(MATCHES)
    review(MATCHES)
    assert _digest(MATCHES) == before


def test_the_police_conversion_gap_that_reordered_the_doctrine(archive):
    """76 chances, 11 taken, and 27 of the misses spent on a barrier."""
    assert archive.chances > 50
    assert archive.converted / archive.chances < 0.25, (
        "if the police were converting, the pounce would not be the headline fix")
    assert archive.lost_to_barrier > archive.converted, (
        "the ordering fix rests on this: we barred more chances than we took")


def test_the_estimator_that_was_replaced_and_the_one_that_replaced_it(archive):
    """The single measurement the whole of v6 turns on.

    The claim to pin is *never wrong*, not *never silent*, and the archive drew
    the distinction itself. This asserted equality until the C001 series against
    uoh-ay26 was filed, which added 15 transitions the inverter declines: all of
    them our own STAY followed by our own STAY, where a stationary emitter
    deposits twice on one cell and the two served fields no longer carry a
    unique difference to solve. It returns None there rather than guessing, and
    `tracking.unique_peak` is built to do exactly that.

    A silence costs the belief fallback for one turn. A wrong fix would send the
    police to the wrong square with full confidence, which is the failure the
    inverter exists to end - so that is the number held at zero, across every
    sub-game, every opponent and all three negotiated models.
    """
    assert archive.fixes > 1500
    # Split by cut before reading any argmax rate. The archive is mixed physics
    # now, and the early cut serves the emission ceiling on the emitter's OWN
    # cell - so there the argmax is not a weak estimate, it is exactly right,
    # and averaging the two together says nothing about either. Taken whole the
    # rate reads 24%, which is neither number.
    late_fixes = archive.fixes - archive.early_cut_fixes
    late_argmax = archive.argmax_right - archive.early_cut_argmax_right
    assert late_fixes > 1500, "the late-cut series are the ones this claim is about"
    assert late_argmax / late_fixes < 0.20, (
        "argmax of the served field was the position estimate both brains used")
    assert archive.early_cut_argmax_right == archive.early_cut_fixes, (
        "under the early cut the peak IS the emitter's cell - if that ever "
        "fails, the cut detection is wrong, not the estimator")
    assert archive.inverse_wrong == 0, (
        f"inverting the model named the WRONG cell {archive.inverse_wrong} times - "
        "a confident wrong fix is worse than no fix")
    assert archive.inverse_right / archive.fixes > 0.99, (
        f"inverting was silent on {archive.fixes - archive.inverse_right} of "
        f"{archive.fixes} transitions - it is meant to answer nearly always")


def test_the_thief_died_where_the_broken_estimator_pointed_it(archive):
    """`max` returns the first tied cell in row-major order - the top-left.

    A thief weighting that at `w_trail` runs the other way, and the deaths are
    on the far edges: not proof of the mechanism, but exactly its signature.
    """
    assert archive.exposures > 30, "it walked into the pursuer's reach routinely"
    # 0.69 when this was written, 0.58 now, and the gate moves with it because
    # the archive grew a SECOND way our thief dies. najamjad's cage sealed it at
    # (2,4) in all three thief windows of the counted series - open ground, not
    # a corner - so the far-edge signature is diluted by new deaths rather than
    # contradicted by them. The claim being pinned is that the edges still
    # dominate, not that the ratio is frozen.
    assert death_corner_share(archive) > 0.55
    assert archive.enclosure_deaths >= 9, (
        "cage deaths are now half our thief losses and need their own number")
    assert (2, 4) in archive.enclosure_death_cells, (
        "the counted najamjad cage, the one currently costing us 20 a window")


def test_the_walls_it_built_against_itself(archive):
    """Turns spent unable to reach the thief at all, behind its own barriers."""
    assert archive.cut_off_turns > 100
    assert archive.barriers_placed > 100


def test_the_report_reads_as_prose(archive):
    text = format_review(archive)
    for phrase in ("chances", "converted", "exposures", "argmax", "inverting the model"):
        assert phrase in text


def _digest(root: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            sha.update(path.name.encode())
            sha.update(str(path.stat().st_size).encode())
    return sha.hexdigest()


def test_the_reconstruction_the_counterfactual_rests_on(archive):
    """The opponent's served field is not archived. Ours is - so check on ours.

    Every claim :mod:`~p2p_pursuit.learn.counterfactual` makes depends on being
    able to rebuild a served field from the trajectory that emitted it, because
    that is the only way the tracker can be shown what it would really have
    seen. The archive stores our own fields and our own cells, so the
    reconstruction is checkable against ground truth on exactly the operation it
    will be trusted for.
    """
    checked = mismatched = 0
    for path in sorted(MATCHES.rglob("log_*.json")):
        log = json.loads(path.read_text(encoding="utf-8"))
        if log.get("report_type") != "sub_game_log":
            continue
        ours = _our_steps(log)
        scented = [s for s in ours if s["scent"]]
        if len(scented) < 3:
            continue
        model = _model_of(scented)
        # BOTH halves of the physics. The packet cut is a per-opponent term that
        # the log does not name, and rebuilding on the wrong one lands every
        # field exactly one decay out: all 126 najamjad fields failed here when
        # the cut was assumed rather than detected.
        rebuilt = served_fields({s["step"]: s["after"] for s in ours}, model,
                                serve_before_decay=_cut_of(scented, model))
        for step in scented:
            checked += 1
            mismatched += rebuilt[step["step"]] != step["scent"]
    assert checked > 2000, f"only {checked} served fields to check against"
    assert mismatched == 0, f"{mismatched} of {checked} rebuilt fields differ from the archive"


def test_the_two_pathologies_the_review_named_are_gone(archive):
    """The 11-of-76 is a fact about the doctrine of the day, not about this one.

    The review counts what was played: 27 of the misses forfeited the move to a
    barrier from a cell adjacent to the thief, and 15 stood still. Re-deciding
    the same 76 states with the shipped vector, both are zero and conversions
    have more than doubled. Pinned so that a fixed defect cannot be rediscovered
    from its own scar - and asserted against `archive` so the two counts are
    always read off the same set of logs.
    """
    now = replay(active(Path("config/doctrine.json")), MATCHES)
    assert now.chances == archive.chances, "the two tools disagree about what a chance is"
    assert archive.lost_to_barrier == 27 and archive.lost_standing_still == 15
    assert now.lost_to_barrier == 0, "still trading a capture for a wall"
    assert now.lost_standing_still == 0, "still standing still beside the thief"
    assert now.converted >= 2 * archive.converted


def test_the_capture_term_is_what_took_the_remainder(archive):
    """`w_pounce` earns its place on this measurement, so this is the measurement.

    The floor cannot be lowered to collect these - the pounce returns, so a
    lower floor stops the pursuit running at all - and the term is the
    alternative. Compared on the same states rather than against a remembered
    number, because the rest of the vector has moved since it was tuned.
    """
    shipped = active(Path("config/doctrine.json"))
    assert shipped.w_pounce > 0, "shipped with the term off"
    without = replay(replace(shipped, w_pounce=0.0), MATCHES)
    assert replay(shipped, MATCHES).converted > without.converted


def test_the_counterfactual_does_not_touch_a_single_byte_either():
    before = _digest(MATCHES)
    replay(active(Path("config/doctrine.json")), MATCHES)
    assert _digest(MATCHES) == before
