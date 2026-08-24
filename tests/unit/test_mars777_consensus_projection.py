"""MaRs-777's §16 scope: the other consensus serialization, and the tie award.

Two independently-wrong-looking digests can be produced from one clean series -
compact-vs-spaced, and with-vs-without the Appendix F consolation - so every
assertion here pins bytes rather than shape.
"""

from __future__ import annotations

import json

import pytest

from p2p_pursuit.domain.crypto import canonical_bytes, sha256_hex, spaced_bytes
from p2p_pursuit.report import consensus
from p2p_pursuit.report.mutual_signature import AGGREGATE_KEYS, SUB_GAME_KEYS, signed_aggregate

US, THEM = "ahk-yosi", "MaRs-777"


def _row(index: int, *, us: int, them: int, winner: str | None,
         result: str = "capture") -> dict:
    """One sub-game as `rt.sub_results` holds it: raw keys AND the signed ones."""
    return {
        "index": index, "ending": result, "winner": "police",
        "cop_score": us, "thief_score": them,
        "sub_game_number": index,
        "roles": {US: "thief", THEM: "police"},
        "result": result,
        "winner_group": winner,
        "score": {US: us, THEM: them},
    }


def _series(*pairs: tuple[int, int, str | None]) -> list[dict]:
    return [_row(i, us=u, them=t, winner=w)
            for i, (u, t, w) in enumerate(pairs, start=1)]


# -- the projection ----------------------------------------------------------
def test_the_signature_projection_has_no_game_uid():
    """The one structural difference from our default family."""
    doc = consensus.signature_consensus_document(
        game_id="MaRs-777-vs-ahk-yosi", rows=_series((20, 5, THEM)),
        my_group=US, their_group=THEM)
    assert list(doc) == ["aggregate", "game_id", "sub_games"] or set(doc) == {
        "game_id", "aggregate", "sub_games"}
    assert "game_uid" not in doc


def test_the_two_projections_disagree_on_the_same_series():
    """Which is the whole reason it is negotiated rather than assumed."""
    rows = _series((20, 5, THEM), (5, 10, US))
    _, uid_sha = consensus.projected_consensus(
        consensus.UID_PROJECTION, game_id="g", game_uid="u", rows=rows,
        my_group=US, their_group=THEM)
    _, sig_sha = consensus.projected_consensus(
        consensus.SIGNATURE_PROJECTION, game_id="g", game_uid="u", rows=rows,
        my_group=US, their_group=THEM)
    assert uid_sha != sig_sha


def test_the_signature_digest_is_spaced_not_compact():
    """Their §16: `json.dumps` defaults. Compact bytes hash to a plausible lie."""
    doc = consensus.signature_consensus_document(
        game_id="MaRs-777-vs-ahk-yosi", rows=_series((20, 5, THEM)),
        my_group=US, their_group=THEM)
    assert consensus.signature_consensus_sha(doc) == sha256_hex(spaced_bytes(doc))
    assert consensus.signature_consensus_sha(doc) != sha256_hex(canonical_bytes(doc))
    # And the bytes really do carry ", " / ": " - not merely a different digest.
    assert b'", "' in spaced_bytes(doc) or b'": "' in spaced_bytes(doc)


def test_the_projected_keys_are_exactly_their_two_tuples():
    doc = consensus.signature_consensus_document(
        game_id="g", rows=_series((20, 5, THEM)), my_group=US, their_group=THEM)
    assert set(doc["aggregate"]) == set(AGGREGATE_KEYS)
    assert set(doc["sub_games"][0]) == set(SUB_GAME_KEYS)


def test_rows_ascend_by_sub_game_whatever_order_they_arrive_in():
    rows = _series((20, 5, THEM), (5, 10, US), (20, 5, THEM))
    shuffled = [rows[2], rows[0], rows[1]]
    doc = consensus.signature_consensus_document(
        game_id="g", rows=shuffled, my_group=US, their_group=THEM)
    assert [r["sub_game_number"] for r in doc["sub_games"]] == [1, 2, 3]


def test_an_unknown_projection_raises_rather_than_defaulting():
    """Settling a series against the wrong bytes must not be a silent fallback."""
    with pytest.raises(ValueError, match="unknown consensus projection"):
        consensus.projected_consensus("mutual", game_id="g", game_uid="u",
                                      rows=_series((20, 5, THEM)),
                                      my_group=US, their_group=THEM)


# -- the tie award -----------------------------------------------------------
def test_the_award_is_off_by_default_so_past_agreements_do_not_move():
    """`mutual_signature` has already been matched with other teams."""
    rows = _series((10, 10, None))
    assert signed_aggregate(rows, my_group=US, their_group=THEM) == \
        signed_aggregate(rows, my_group=US, their_group=THEM, tie_award=0)
    assert signed_aggregate(rows, my_group=US, their_group=THEM)["total_score"] \
        == {US: 10, THEM: 10}


def test_the_award_lands_only_when_the_series_is_level():
    level = signed_aggregate(_series((10, 10, None)), my_group=US,
                             their_group=THEM, tie_award=2)
    assert level["total_score"] == {US: 12, THEM: 12}
    assert level["series_tie"] is True

    decided = signed_aggregate(_series((20, 5, THEM)), my_group=US,
                               their_group=THEM, tie_award=2)
    assert decided["total_score"] == {US: 20, THEM: 5}
    assert decided["series_tie"] is False


def test_a_drawn_row_alone_earns_no_award():
    """Their §5: never on a drawn row - only on level series totals."""
    rows = _series((20, 5, THEM), (0, 0, None))
    agg = signed_aggregate(rows, my_group=US, their_group=THEM, tie_award=2)
    assert agg["ties"] == 1                 # the drawn row still counts as a tie
    assert agg["series_tie"] is False       # but the series is not level
    assert agg["total_score"] == {US: 20, THEM: 5}


def test_the_award_reaches_total_score_and_nothing_else():
    """`sub_games_won` and `ties` never see it - the divergence they warned of."""
    rows = _series((20, 5, THEM), (5, 20, US))
    plain = signed_aggregate(rows, my_group=US, their_group=THEM)
    awarded = signed_aggregate(rows, my_group=US, their_group=THEM, tie_award=2)
    assert plain["series_tie"] is True
    moved = {k for k in AGGREGATE_KEYS if plain[k] != awarded[k]}
    assert moved == {"total_score"}


def test_winner_group_is_derived_before_the_award_not_after():
    """Adding 2 to both sides cannot flip it - this pins that we never re-derive."""
    rows = _series((20, 5, THEM))
    agg = signed_aggregate(rows, my_group=US, their_group=THEM, tie_award=2)
    assert agg["winner_group"] == US        # 20 > 5, from the raw totals
    assert agg["total_score"] == {US: 20, THEM: 5}


def test_the_award_rides_the_signature_projection_only():
    """`projected_consensus` is where the two decisions meet."""
    rows = _series((10, 10, None))
    doc, _ = consensus.projected_consensus(
        consensus.SIGNATURE_PROJECTION, game_id="g", game_uid="u", rows=rows,
        my_group=US, their_group=THEM, tie_award=2)
    assert doc["aggregate"]["total_score"] == {US: 12, THEM: 12}

    uid_doc, _ = consensus.projected_consensus(
        consensus.UID_PROJECTION, game_id="g", game_uid="u", rows=rows,
        my_group=US, their_group=THEM, tie_award=2)
    assert "aggregate" not in uid_doc       # the award has nowhere to land here


def test_their_worked_envelope_shape_is_unchanged_by_the_projection():
    """Same envelope, same claim, same empty records - only the digest moves."""
    envelope = consensus.consensus_envelope(sender="police", sha="a" * 64)
    assert json.loads(json.dumps(envelope)) == {
        "sender": "police", "records": [], "result_claim": "series_consensus",
        "consensus_sha": "a" * 64}
    assert consensus.peer_consensus_sha(envelope, peer_role="police") == "a" * 64
