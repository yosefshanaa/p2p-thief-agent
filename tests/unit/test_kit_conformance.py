"""Our implementation against `copthief-league-protocol`'s CORE vectors.

The kit exists because the opponent re-hashes our records at the audit, so two
honest peers whose serializers differ can each conclude the other cheated and
both score 0 - and nothing local reveals it. Several teams in this league now
build against these vectors, which makes them the closest thing to a shared
wire contract we have.

The direction matters: these tests feed *their* published inputs to *our*
functions, never to theirs. Vendored data only, provenance in
`tests/vectors/kit/README.md`.

Overlaps `test_interop_guide_vectors.py` by design - that one pins the numbers
we *publish*, this one pins the numbers another implementation *expects*. The
two agreeing is the whole claim, and a change that breaks only one of them is
exactly the change worth stopping.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from p2p_pursuit.domain.crypto import canonical_bytes, reference_commit
from p2p_pursuit.domain.game_ids import reference_game_id, reference_game_uid

VECTORS = Path(__file__).resolve().parents[1] / "vectors" / "kit"


def _load(name: str) -> dict[str, Any]:
    return json.loads((VECTORS / f"{name}.json").read_text(encoding="utf-8"))


def _cases(name: str, key: str = "vectors") -> list[Any]:
    return _load(name)[key]


@pytest.mark.parametrize("vector", _cases("canonical_json"))
def test_canonical_form_matches_the_kit(vector: dict[str, Any]) -> None:
    """Byte-for-byte, not merely equal digests - the bytes are the contract."""
    encoded = canonical_bytes(vector["object"])
    assert encoded.decode("utf-8") == vector["canonical"], vector.get("note")
    assert hashlib.sha256(encoded).hexdigest() == vector["sha256"]


@pytest.mark.parametrize("vector", _cases("commit_reveal"))
def test_commit_seal_matches_the_kit(vector: dict[str, Any]) -> None:
    assert reference_commit(vector["payload"], vector["nonce"]) == vector["commit"], (
        vector.get("note"))


@pytest.mark.parametrize("vector", _cases("game_uid"))
def test_match_ids_match_the_kit(vector: dict[str, Any]) -> None:
    """Both ids sort the pair, so neither peer has to be told which name to use."""
    a, b = vector["group_a"], vector["group_b"]
    assert reference_game_uid(vector["terms"], a, b) == vector["game_uid"]
    assert reference_game_id(a, b) == vector["game_id"]


@pytest.mark.parametrize("vector", _cases("terms_signature"))
def test_terms_signature_is_our_commit_over_the_terms(vector: dict[str, Any]) -> None:
    """Their pre-game gate is the commit construction applied to the terms."""
    assert reference_commit(vector["terms"], vector["nonce"]) == vector["signature"]


@pytest.mark.parametrize("vector", _cases("report_consensus"))
def test_settlement_digest_uses_the_spaced_encoding(vector: dict[str, Any]) -> None:
    """The second canonical form: `json.dumps` DEFAULTS, not the compact commit
    separators. Getting this one wrong is invisible until settlement, when two
    correctly-played series disagree on a digest neither side can debug."""
    from p2p_pursuit.domain.crypto import spaced_bytes

    body = vector["report"]
    assert hashlib.sha256(spaced_bytes(body)).hexdigest() == vector["signature"]
    compact = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(compact.encode("utf-8")).hexdigest() == vector["compact_form_sha256"]


def test_the_negotiated_term_set_is_the_same_fourteen() -> None:
    """Same keys, whatever the values: a term we do not send cannot be agreed,
    and one we send that they do not expect fails their signature check."""
    from p2p_pursuit.infra.interop_codec import interop_terms
    from p2p_pursuit.shared.config import load_role

    base = Path(__file__).resolve().parents[2]
    shared, _peer = load_role(base / "config" / "police")
    theirs = _cases("game_uid")[0]["terms"]
    assert set(interop_terms(shared)) == set(theirs)
