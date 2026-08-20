"""Two peers must reach the same `game_id`/`game_uid`, whatever dialect they speak.

The pair is the first two keys of both cross-checks a series settles on - the
`mutual_signature` written into every result, and the §10.3 consensus document -
so a pair that is not shared makes those digests differ by construction, however
perfectly the two sides agree on the score.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2p_pursuit.domain.game_ids import (
    UNKNOWN_GROUP,
    make_game_id,
    reference_game_id,
    reference_game_uid,
)
from p2p_pursuit.infra.interop_codec import interop_terms
from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent
OURS, THEIRS = "ahk-yosi", "uoh-other"


def _peers(tmp_path: Path) -> tuple[PeerRuntime, PeerRuntime]:
    police = PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path, seed=1)
    thief = PeerRuntime("thief", BASE / "config" / "thief", out_dir=tmp_path, seed=2)
    return police, thief


def _handshake(group_id: str | None) -> dict:
    return {"group_id": group_id} if group_id is not None else {}


def _derived_uid(rt: PeerRuntime) -> str:
    terms = interop_terms(rt.shared, num_games=rt.signed_num_games)
    return reference_game_uid(terms, OURS, THEIRS)


def test_the_minted_id_carries_a_clock_and_so_cannot_be_shared() -> None:
    """Why the derivation exists at all.

    `make_game_id` stamps to the second. Two peers agree only when their two
    constructions land inside the same second - a coin toss inside one process,
    and never at all across two machines a league match actually runs on.
    """
    now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    assert make_game_id(OURS, THEIRS, now) == make_game_id(OURS, THEIRS, now)
    later = now + timedelta(seconds=1)
    assert make_game_id(OURS, THEIRS, now) != make_game_id(OURS, THEIRS, later), (
        "a one-second skew must change the id - if it does not, this test is "
        "no longer measuring the defect it was written for")


def test_both_peers_derive_the_same_pair_from_opposite_chairs(tmp_path) -> None:
    police, thief = _peers(tmp_path)
    # Locally minted, before either has heard of the other: two different pairs.
    assert police.game_uid != thief.game_uid

    police._adopt_shared_ids(_handshake(THEIRS))
    thief.peer = dataclasses.replace(thief.peer, group_id=THEIRS)
    thief._adopt_shared_ids(_handshake(OURS))

    assert police.game_id == thief.game_id == reference_game_id(OURS, THEIRS)
    assert police.game_uid == thief.game_uid
    # Derived, not exchanged: the value is a function of the agreed terms and
    # the two slugs, so neither side had to be told it.
    assert police.game_uid == _derived_uid(police)


def test_the_native_dialect_adopts_too(tmp_path) -> None:
    """The regression this file exists for.

    Adoption used to be gated on speaking the reference dialect, later on that
    or `series_consensus`. Our shipped config is `native` with consensus off -
    the one combination both gates excluded - so every native match signed a
    `mutual_signature` over an id the opponent could not reproduce. It stayed
    invisible only because every opponent so far speaks the reference dialect.
    """
    police, _ = _peers(tmp_path)
    assert police.peer.interop_dialect == "native" and not police.peer.series_consensus
    minted = police.game_id
    police._adopt_shared_ids(_handshake(THEIRS))
    assert police.game_id != minted
    assert police.game_id == reference_game_id(OURS, THEIRS)


@pytest.mark.parametrize("slug", [None, "", UNKNOWN_GROUP])
def test_an_unnamed_opponent_leaves_our_own_pair_alone(tmp_path, slug) -> None:
    """A placeholder agrees with nobody.

    Deriving against "opponent" would still not match them - they would derive
    against *their* slug and ours - while throwing away the locally unique pair
    we already hold. So an opponent that will not name itself is a stop.
    """
    police, _ = _peers(tmp_path)
    minted_id, minted_uid = police.game_id, police.game_uid
    police._adopt_shared_ids(_handshake(slug))
    assert (police.game_id, police.game_uid) == (minted_id, minted_uid)


def test_the_agreed_label_overrides_the_id_but_never_the_uid(tmp_path) -> None:
    """`P2P_GAME_ID` is how two teams name a demo match; the uid still proves
    they signed the same terms, so the label must not be able to forge it."""
    police, _ = _peers(tmp_path)
    police.peer = dataclasses.replace(police.peer, game_id_label="AHK-DEMO1")
    police._adopt_shared_ids(_handshake(THEIRS))
    assert police.game_id == "AHK-DEMO1"
    assert police.game_uid == _derived_uid(police)


def test_the_output_directory_stays_unique_per_run(tmp_path) -> None:
    """The derived id is deterministic, so it cannot also name the directory:
    a warm-up would overwrite the sealed logs of the counted match against the
    same opponent. Filenames keep the agreed id; the directory gets the stamp."""
    police, _ = _peers(tmp_path)
    police._adopt_shared_ids(_handshake(THEIRS))
    assert police.out_dir.name.startswith(f"police-{reference_game_id(OURS, THEIRS)}-")
    assert police.out_dir.name != f"police-{police.game_id}"
