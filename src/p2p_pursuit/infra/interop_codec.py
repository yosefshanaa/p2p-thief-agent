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
from typing import Any

from ..domain.crypto import reference_commit
from ..domain.game_ids import UNKNOWN_GROUP
from ..domain.rules import POLICE, THIEF
from ..shared import sysinfo
from ..shared.config_env import WIRE_ROLE_NAMES

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
def interop_identity(peer: Any, *, mcp_url: str, spec: dict[str, Any],
                     counted_games_played: int = 0,
                     public_doors: dict[str, str] | None = None) -> dict[str, Any]:
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

    ``git_commit_hash`` is the same courtesy for the commit. uoh-ay26 gate their
    negotiation on a **top-level** field of exactly that name holding 40
    lowercase hex, and refuse the offer without it; the step-0 `system_spec`
    record we already seal spells the same value `github_commit`, which is what
    amireman reads. Neither spelling is more correct, so both go out - the cost
    is one key and the alternative is a refusal at negotiation for a value we
    were always willing to publish.

    ``mcp_servers`` is the address an opponent dials us back on, and it is worth
    more care than it looks. ``mcp_url`` is what the process can see - the
    address it *binds*, which behind a tunnel is `0.0.0.0:<port>` and reachable
    by nobody. Publishing it named one unreachable door for both roles while we
    in fact run two processes on two ports, so a peer whose handshake recovery
    re-sends its agreement "to the address your identity declares" (najamjad
    §3.1) dials a loopback address twice and reads us as offline. `public_doors`
    carries the real per-role URLs when the deployment knows them; the bind
    address remains the fallback, which is honest for a local match.
    """
    commit = sysinfo.git_commit()
    doors = {WIRE_ROLE_NAMES.get(role, role): url
             for role, url in (public_doors or {}).items() if url}
    return {
        "group_id": peer.group_id,
        "group_name": peer.group_name,
        "members": list(peer.members),
        "repos": dict(peer.repos),
        "mcp_servers": {"cop": doors.get("cop", mcp_url),
                        "thief": doors.get("thief", mcp_url)},
        "llm_model": peer.llm_model or "template",
        "counted_games_played": counted_games_played,
        "prior_counted_games": counted_games_played,
        "git_commit_hash": commit,
        "github_commit": commit,
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
        "group_id": identity.get("group_id", UNKNOWN_GROUP),
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


# -- their commit formula ----------------------------------------------------


# The reference dialect's own wire format lives in `.interop_reference`; the
# names stay reachable here because callers reach this module as `codec.X`.
from .interop_grid import grid_to_scent, scent_to_grid  # noqa: E402
from .interop_reference import (  # noqa: E402
    from_turn_message,
    reference_audit,
    reference_records,
    reference_verify,
    to_turn_message,
)
