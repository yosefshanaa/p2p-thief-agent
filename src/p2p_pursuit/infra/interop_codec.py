"""Translation between our protocol and a reference-derived peer's.

Pure functions, no I/O: the bridge that owns sockets and inboxes is elsewhere.
Two shapes are being reconciled, both taken from the reference source rather
than guessed:

* **Granularity.** We send commit, then reveal, then any event. It sends one
  ``TurnMessage`` per turn carrying the commit hash *and* the public reveal,
  with claim answers and win claims riding along on the following message.
* **The digest.** Ours hashes the record with the nonce inside it; theirs
  hashes ``canonical(payload)|nonce``. The formulas are NOT interchangeable,
  so :func:`reference_commit` exists to verify their log on their terms.

Its ``TurnMessage.from_dict`` does ``cls(**data)``, so an extra key is a
TypeError on their side: :func:`to_turn_message` emits exactly their fields.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..domain.crypto import reference_commit, verify_reference_record
from ..domain.rules import POLICE, THIEF

log = logging.getLogger(__name__)

Matrix = list[list[float]]

__all__ = ["from_turn_message", "grid_to_scent", "interop_terms", "reference_audit",
           "reference_commit", "reference_records", "reference_verify", "scent_to_grid",
           "to_turn_message"]


def interop_terms(shared: Any, *, num_games: int | None = None) -> dict[str, Any]:
    """Our constitution expressed in their agreed-terms vocabulary.

    Their ``verify_peer`` compares terms by dict equality, so every value must
    match theirs exactly - this is the mapping to agree, field by field, in the
    warm-up before a counted match.
    """
    ph = shared.pheromones
    return {
        "board_size": shared.grid_size,
        "smell_grid_size": ph["pheromone_grid_size"],
        "decay_per_step": ph["pheromone_decay"],
        "emit_intensity": ph["pheromone_center_intensity"],
        # A floor their SmellField validates emissions against, not a knob:
        # our fixed 0.9 emission centre satisfies it (see the interop notes).
        "min_center_intensity": ph.get("pheromone_min_center_intensity", 0.5),
        "max_steps": shared.max_moves,
        "barriers_max": shared.max_barriers,
        "setting": shared.map_area,
        "hint_max_words": shared.hint_max_words,
        "axis_origin_corner": shared.raw["board_and_agents"].get(
            "axis_origin_corner", "top-left"),
        "axis_start_index": shared.raw["board_and_agents"].get("axis_start_index", 0),
        "thief_start": list(shared.thief_start),
        "cop_start": list(shared.cop_start),
        # The series length actually being played, which --games may override:
        # signing the config default would break agreement on a shorter warm-up.
        "num_games": shared.num_games if num_games is None else num_games,
    }


# -- scent field -------------------------------------------------------------
def scent_to_grid(matrix: Matrix) -> dict[str, float]:
    """Our dense matrix -> their sparse ``{"r,c": intensity}`` (zeros dropped)."""
    return {f"{r},{c}": value
            for r, row in enumerate(matrix)
            for c, value in enumerate(row) if value > 0.0}


def grid_to_scent(grid: dict[str, Any], size: int) -> Matrix:
    """Their sparse grid -> our dense ``size``x``size`` matrix (unknown cells 0.0)."""
    matrix: Matrix = [[0.0] * size for _ in range(size)]
    for key, value in grid.items():
        r, c = (int(part) for part in str(key).split(","))
        if 0 <= r < size and 0 <= c < size:
            matrix[r][c] = float(value)
    return matrix


def interop_identity(peer: Any, *, mcp_url: str, spec: dict[str, Any],
                     counted_games_played: int = 0) -> dict[str, Any]:
    """Our group identity in the shape their declaration builder demands.

    Their ``group_block`` indexes ``mcp_servers``, ``llm_model`` and ``spec``
    directly: omitting any of them crashes their reporting *after* a completed
    game, which is exactly how the first warm-up ended. Their hardware block
    also reads different spec key names than ours, so those are mapped here
    rather than left to come out null in their declaration.

    ``counted_games_played`` is *their* spelling of our truthful rule-#37
    declaration, and the identity block is the only place it crosses this
    dialect's wire. An opponent reads it straight into the counter it files for
    us, so omitting it does not mean "unknown" on their side - it means they
    invent a number on our behalf. Both spellings are sent: ours so a native
    reader is unaffected, theirs so a reference reader is correct.
    """
    return {
        "group_id": peer.group_id,
        "group_name": peer.group_name,
        "members": list(peer.members),
        "repos": dict(peer.repos),
        "mcp_servers": {"cop": mcp_url, "thief": mcp_url},
        "llm_model": peer.llm_model or "template",
        "counted_games_played": counted_games_played,
        "prior_counted_games": counted_games_played,
        "spec": {**spec, "cpu_model": spec.get("machine", ""),
                 "gpu_type": spec.get("gpu", "none")},
    }


def _log_agreement_gap(agreement: dict[str, Any], *, terms: dict[str, Any],
                       signed: bool) -> None:
    """Say exactly WHY an agreement failed, at the moment it fails.

    Without this, a terms difference and a bad signature both surface later as
    the same pair of downstream errors ("constitution mismatch" + "scent model
    mismatch"), because the lock fields are simply absent - two messages naming
    neither the field nor the real cause. A mismatch you cannot name costs a
    turn timeout to diagnose; named, it costs a log line.
    """
    theirs = agreement.get("terms", {})
    if theirs != terms:
        keys = sorted(set(theirs) | set(terms))
        diff = [f"{k}: ours={terms.get(k, '<absent>')!r} theirs={theirs.get(k, '<absent>')!r}"
                for k in keys if theirs.get(k) != terms.get(k)]
        log.warning("agreement TERMS differ from ours on %d field(s): %s",
                    len(diff), "; ".join(diff))
    if not signed:
        log.warning("agreement SIGNATURE did not verify: their signature=%r over "
                    "%d terms keys with nonce=%r",
                    agreement.get("signature"), len(theirs), agreement.get("nonce"))
    sub_game = agreement.get("sub_game_number")
    if sub_game is not None:
        log.info("agreement is for sub-game %s (identity %s)",
                 sub_game, agreement.get("identity", {}).get("group_id"))


def handshake_from_agreement(agreement: dict[str, Any], *, mine: dict[str, Any],
                             terms: dict[str, Any]) -> dict[str, Any]:
    """Their signed agreement, expressed as one of our handshake payloads.

    Their message carries no constitution hash, no scent-model lock and no
    role: in this dialect the constitution *is* the terms dict, agreed by exact
    equality and a signature over it. So the two lock fields are mirrored from
    ours only when their terms match ours exactly *and* their signature checks
    out - otherwise they are left absent and ``check_compatibility`` refuses
    the match, which is precisely the wanted behaviour. ``first_mover`` states
    a fact about their implementation (its thief always opens) rather than
    copying our own value, so a real disagreement is still caught.
    """
    identity = agreement.get("identity", {})
    signed = reference_commit(agreement.get("terms", {}),
                              agreement.get("nonce", "")) == agreement.get("signature")
    _log_agreement_gap(agreement, terms=terms, signed=signed)
    payload: dict[str, Any] = {
        "kind": "handshake",
        "role": THIEF if mine.get("role") == POLICE else POLICE,
        "group_id": identity.get("group_id", "opponent"),
        "group_name": identity.get("group_name", ""),
        "members": list(identity.get("members", [])),
        "repos": dict(identity.get("repos", {})),
        "code_version": identity.get("code_version", ""),
        "first_mover": THIEF,
        "game_id": mine.get("game_id", ""),
        "game_uid": mine.get("game_uid", ""),
        "counted": mine.get("counted", False),
        # Their spelling first: a reference peer sends only `counted_games_played`,
        # so reading our own name alone silently files a 0 we invented for them.
        "prior_counted_games": int(identity.get("counted_games_played",
                                                identity.get("prior_counted_games", 0)) or 0),
        "dialect": "reference",
        "terms_match": agreement.get("terms") == terms,
        "signature_verified": signed,
        "sub_game_number": agreement.get("sub_game_number"),
        # Absence is not disagreement. An empty agreement makes every term look
        # mismatched and the signature look forged, so the caller is told it
        # received *nothing* rather than being handed 14 false differences and
        # two misleading refusal messages (measured live, uoh-sqak 2026-08-10).
        "agreement_empty": not agreement.get("terms") and not agreement.get("signature"),
    }
    if payload["terms_match"] and signed:
        payload["config_sha256"] = mine.get("config_sha256")
        payload["scent_model_sha256"] = mine.get("scent_model_sha256")
    return payload


# -- our commit + reveal -> their TurnMessage --------------------------------
def to_turn_message(reveal: dict[str, Any], *, commit_hash: str | None = None,
                    claim_response: dict | None = None,
                    win_claim: dict | None = None,
                    timestamp: str | None = None) -> dict[str, Any]:
    """Fold one of our steps into the single message their peer expects.

    ``claim_response`` and ``win_claim`` are what we owe them from *their*
    previous message; their protocol carries both as plain fields on the next
    turn, so neither is bound by their commit (see the interop notes).
    """
    claim = reveal.get("claim")
    return {
        "step": reveal["step"],
        "sender": reveal["role"],
        "hint": reveal.get("hint", ""),
        "smell_grid": scent_to_grid(reveal.get("scent") or []),
        "commit": commit_hash or reveal.get("hash", ""),
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "barrier_placed": list(reveal["barrier"]) if reveal.get("barrier") else None,
        "capture_claim": list(claim["cell"]) if claim else None,
        "claim_response": claim_response,
        "win_claim": win_claim,
    }


# -- their TurnMessage -> our commit + reveal --------------------------------
def from_turn_message(message: dict[str, Any], *, sub_game: int,
                      grid_size: int) -> dict[str, Any]:
    """Split their turn into the two messages our engine handlers consume.

    Returns ``{commit, reveal, claim_response, win_claim}``; the last two are
    side channels the engine has no inbound handler for, so the bridge applies
    them itself.
    """
    sender, step = message["sender"], message["step"]
    commit_hash = message.get("commit", "")
    reveal: dict[str, Any] = {
        "kind": "step", "role": sender, "sub_game": sub_game, "step": step,
        "barrier": list(message["barrier_placed"]) if message.get("barrier_placed") else None,
        "hint": message.get("hint", ""),
        "scent": grid_to_scent(message.get("smell_grid") or {}, grid_size),
        "hash": commit_hash,
        # Their clock, stamped by them on the turn itself. Outside their commit
        # and therefore untrusted as evidence - but it is the only timing in the
        # match sourced from the other side, so it is kept and filed as theirs
        # rather than discarded.
        "timestamp": message.get("timestamp"),
    }
    if message.get("capture_claim"):
        reveal["claim"] = {"cell": list(message["capture_claim"]), "at_step": step}
    return {
        "commit": {"kind": "commit", "role": sender, "sub_game": sub_game,
                   "step": step, "hash": commit_hash},
        "reveal": reveal,
        "claim_response": message.get("claim_response"),
        "win_claim": message.get("win_claim"),
    }


# -- their commit formula ----------------------------------------------------
# The formula itself lives in domain.crypto, which owns every digest in the
# system; these helpers wrap it in the record envelope their audit expects.
def reference_records(sealed_records: list[dict[str, Any]],
                      live_hashes: list[str] | None = None) -> list[dict[str, Any]]:
    """Our sealed records -> their ``{payload, nonce, commit}`` audit format.

    Only the envelope changes: the payload is our record, so what we committed
    to is exactly what we played.

    ``commit`` is the commitment **we actually sent live**, not one re-derived
    here. Re-deriving is what makes a broken reveal look healthy: every record
    still verifies against its own recomputed hash, so the package passes any
    self-check, while binding to nothing the opponent holds. Recomputation is
    still done - as a comparison, so a divergence is a loud mismatch at the
    moment of sending instead of a silent 0-of-N in their audit.
    """
    hashes = list(live_hashes or [])
    out = []
    for index, sealed in enumerate(sealed_records):
        payload = {k: v for k, v in sealed.items() if k != "nonce"}
        derived = reference_commit(payload, sealed["nonce"])
        live = hashes[index] if index < len(hashes) else None
        if live is not None and live != derived:
            log.error("record %d: the sealed payload no longer hashes to the "
                      "commitment we sent (%s != %s) - revealing the live one",
                      index, derived[:16], live[:16])
        out.append({"payload": payload, "nonce": sealed["nonce"],
                    "commit": live or derived})
    return out


def reference_verify(record: dict[str, Any]) -> bool:
    """Re-hash one revealed ``{payload, nonce, commit}`` record on their terms."""
    return verify_reference_record(record)


def reference_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a whole reference-format log; mirrors their ``audit_records`` report."""
    failed = [record["payload"].get("step", -1)
              for record in records if not reference_verify(record)]
    return {"passed": not failed, "verified_steps": len(records) - len(failed),
            "failed_steps": failed}
