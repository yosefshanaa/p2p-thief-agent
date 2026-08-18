"""Sealed-record shapes for the commit-reveal protocol.

Interpretation (documented in the README interpretation log): the per-step
Reveal discloses only the *public projection* - hint, served scent field and
barrier declarations. Move, positions, intent and nonce stay sealed until the
sub-game audit; a per-step move reveal would collapse the partial-observability
premise the whole book is built on.
"""

from __future__ import annotations

from typing import Any

from .board import Cell

KIND_STEP = "step"
KIND_CAPTURE_ANSWER = "capture_answer"
KIND_CAPTURED_EVENT = "captured_event"
KIND_SURVIVAL_CLAIM = "survival_claim"

PRIVATE_FIELDS = ("pos_before", "pos_after", "move", "intent", "nonce")

#: The reference family's spelling of ``sub_game``. Mirrored into every sealed
#: record so a peer auditing us can bucket our reveal by *content* instead of by
#: arrival time. Bucketing an audit package by when it lands is unsound - the
#: two peers cross a sub-game boundary at different instants - and it is what
#: made amireman file our sub-game N reveal against their sub-game N+1: 0 of N
#: commitments bound, and under role alternation every role label read inverted.
#: Sealed with the record, never added at audit time, so it is covered by the
#: same commitment as everything else in the payload.
SUB_GAME_KEY = "sub_game_number"


def _sub_game_keys(sub_game: int) -> dict[str, int]:
    return {"sub_game": sub_game, SUB_GAME_KEY: sub_game}


def step_record(
    *,
    role: str,
    sub_game: int,
    step: int,
    pos_before: Cell,
    pos_after: Cell,
    move: str,
    barrier: Cell | None,
    intent: str,
    hint: str,
    scent: list[list[float]],
) -> dict[str, Any]:
    """The full record that gets sealed for one step (nonce added by crypto.seal).

    ``state`` and ``position`` are the reference family's names for where the
    mover ended up, and both are carried alongside our own ``pos_after``.

    They are not decoration. Every reference peer whose logs we hold publishes
    one or both - gal-roy1 a bare ``[3, 4]``, amireman the string
    ``"grid=7;self=[4, 3]"``, s82kma9e both - and a validator that reconstructs
    the trajectory reads ``state``. Ours had neither, so uoh-ay26's audit saw
    ``state: None`` on every police step of a sub-game that otherwise played
    perfectly, could not verify continuity, and disabled mutual sign-off. Three
    earlier opponents never checked, which is why a missing field survived four
    counted matches: an omission only fails against the peer that looks.

    Duplicating a value we already send is cheap; being unverifiable is not.
    """
    return {
        "kind": KIND_STEP,
        "role": role,
        **_sub_game_keys(sub_game),
        "step": step,
        "pos_before": list(pos_before),
        "pos_after": list(pos_after),
        "state": list(pos_after),
        "position": list(pos_after),
        "move": move,
        "barrier": list(barrier) if barrier else None,
        "intent": intent,
        "hint": hint,
        "scent": scent,
    }


def capture_answer_record(
    *, role: str, sub_game: int, at_step: int, claim_cell: Cell, answer: bool
) -> dict[str, Any]:
    """The thief's cryptographically bound truthful answer to a Capture Claim (#21)."""
    return {
        "kind": KIND_CAPTURE_ANSWER,
        "role": role,
        **_sub_game_keys(sub_game),
        "at_step": at_step,
        "claim_cell": list(claim_cell),
        "answer": answer,
    }


def captured_event_record(*, role: str, sub_game: int, at_step: int, cause: str) -> dict[str, Any]:
    """Forced honest confession: barrier landed on us (#46) or we are enclosed (#47)."""
    return {
        "kind": KIND_CAPTURED_EVENT,
        "role": role,
        **_sub_game_keys(sub_game),
        "at_step": at_step,
        "cause": cause,
    }


def survival_claim_record(*, role: str, sub_game: int, steps: int) -> dict[str, Any]:
    return {"kind": KIND_SURVIVAL_CLAIM, "role": role,
            **_sub_game_keys(sub_game), "steps": steps}


def record_sub_game(record: dict[str, Any]) -> int | None:
    """Which sub-game a sealed record (ours or a reference peer's) belongs to.

    Reads both spellings, because this is the question an audit has to answer
    about a record it did not write.
    """
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
    for key in ("sub_game", SUB_GAME_KEY):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def public_view(sealed: dict[str, Any], commit_hash: str) -> dict[str, Any]:
    """The reveal payload: everything except the sealed-private fields, plus the hash."""
    pub = {k: v for k, v in sealed.items() if k not in PRIVATE_FIELDS}
    pub["hash"] = commit_hash
    return pub
