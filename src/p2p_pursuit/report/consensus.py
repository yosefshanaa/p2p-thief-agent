"""The canonical series-consensus object and its exchange (amireman guide §10-11).

A third cross-team digest, and deliberately a separate module from
:mod:`.mutual_signature` rather than a flag on it. Both reduce a finished series
to a group-keyed projection so two independent implementations can agree without
sharing a schema, and they are *not* interchangeable:

============  =============================  ==================================
              mutual signature (uoh-sqak)     series consensus (amireman)
============  =============================  ==================================
top level     ``game_id``/``aggregate``/      ``game_id``/``game_uid``/
              ``sub_games``                   ``sub_games`` - no aggregate
encoding      ``json.dumps`` **defaults**     compact ``(",", ":")``
``result``    ``technical_loss`` aliased      ``technical_loss`` is a legal
              to ``timeout``                  value and must survive verbatim
exchanged     inside the filed result         its own end-of-series envelope
============  =============================  ==================================

Any one of those three differences yields a wrong-but-plausible 64-hex string,
which is the failure mode worth designing against: a mismatched digest is
indistinguishable from a genuine disagreement about what was played.
"""

from __future__ import annotations

import re
from typing import Any

from ..domain.crypto import canonical_bytes, sha256_hex

__all__ = ["CONSENSUS_CLAIM", "RESULT_VALUES", "ROW_KEYS", "consensus_document",
           "consensus_envelope", "consensus_row", "consensus_sha", "peer_consensus_sha"]

#: Their ``result_claim`` for the end-of-series envelope, which is what
#: distinguishes it from the per-sub-game audits sharing the same tool.
CONSENSUS_CLAIM = "series_consensus"

#: Exactly five keys per row, keyed by group id so sorted-key JSON is
#: byte-identical on both sides - a role-keyed total cannot be compared between
#: two teams at all once roles alternate.
ROW_KEYS = ("sub_game_number", "result", "roles", "score", "winner_group")

#: Their ``result`` vocabulary. Ours is a subset: we never file ``tamper_forfeit``
#: (a tampered log is a ``technical_loss`` on our side) and ``timeout`` reaches us
#: only from their classification. Unknown values raise rather than being coerced -
#: a silently-mapped result is a silently-wrong digest.
RESULT_VALUES = frozenset({"capture", "survival", "timeout", "technical_loss",
                           "tamper_forfeit"})

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def consensus_row(row: dict[str, Any]) -> dict[str, Any]:
    """Project one of our sub-game rows onto their five keys.

    ``result`` is read from our raw ``ending``, never from the ``result`` that
    :func:`~.mutual_signature.signed_row_fields` writes alongside it: that one is
    already aliased for a peer whose vocabulary has no ``technical_loss``, and
    reusing it here would file a sub-game we lost on protocol as a timeout.
    """
    ending = row.get("ending")
    if ending not in RESULT_VALUES:
        raise ValueError(f"sub-game {row.get('index')}: {ending!r} is not one of "
                         f"{sorted(RESULT_VALUES)}")
    return {
        "sub_game_number": row["index"],
        "result": ending,
        "roles": dict(row["roles"]),
        "score": dict(row["score"]),
        "winner_group": row.get("winner_group"),
    }


def consensus_document(*, game_id: str, game_uid: str,
                       rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The three-key object both sides hash. Rows ascend by sub-game number."""
    ordered = sorted(rows, key=lambda r: r["index"])
    return {"game_id": game_id, "game_uid": game_uid,
            "sub_games": [consensus_row(row) for row in ordered]}


def consensus_sha(document: dict[str, Any]) -> str:
    """SHA-256 over the compact canonical bytes - their §11 serialization."""
    return sha256_hex(canonical_bytes(document))


def consensus_envelope(*, sender: str, sha: str | None) -> dict[str, Any]:
    """The ``submit_audit`` payload that carries our digest.

    ``sender`` is the **wire role**, not a group id, and ``records`` is empty:
    those two plus the claim string are what let their peer tell this envelope
    apart from a per-sub-game audit arriving on the same tool. A missing digest
    is omitted entirely rather than sent as null (their §9).
    """
    envelope: dict[str, Any] = {"sender": sender, "records": [],
                                "result_claim": CONSENSUS_CLAIM}
    if sha:
        envelope["consensus_sha"] = sha
    return envelope


def peer_consensus_sha(payload: dict[str, Any], *,
                       peer_role: str | None = None) -> str | None:
    """Their digest, or ``None`` if the envelope does not pass their own gate.

    Their §10.3 accepts a peer digest **only** when the claim, the sender role
    and the empty record list all hold; §9 additionally ignores a
    ``consensus_sha`` that is not exactly 64 lowercase hex. Enforced on our side
    too, so that a malformed or misrouted envelope reads as "no digest received"
    rather than as a mismatch against ours.

    ``peer_role=None`` checks everything except who sent it - for the caller
    that has already refused strictly and is deciding whether the role alone is
    worth losing the confirmation over.
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("result_claim") != CONSENSUS_CLAIM:
        return None
    if peer_role is not None and payload.get("sender") != peer_role:
        return None
    if payload.get("records") != []:
        return None
    sha = payload.get("consensus_sha")
    return sha if isinstance(sha, str) and _SHA_RE.match(sha) else None
