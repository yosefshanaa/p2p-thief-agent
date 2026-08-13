"""Series-level conventions that differ between implementations.

Neither of these is settled by the book - the sub-game count is a placeholder in
the spec and role alternation is unspecified - so both are pair-negotiated, like
the wire dialect, and both default to off. Getting either wrong voids a match
from sub-game 2 onward while sub-game 1 looks perfect, which is exactly how a
one-sub-game warm-up passes and a six-sub-game counted match dies (RUNBOOK 3b).
"""

from __future__ import annotations

from typing import Any

from ..domain.rules import POLICE, THIEF


def role_for(natural: str, sub_game: int) -> str:
    """Natural role on odd sub-games, the opposite on even ones.

    Matches the reference implementation's ``role_for`` so an alternating series
    stays in step with it rather than colliding on the same role.
    """
    if sub_game % 2 == 1:
        return natural
    return THIEF if natural == POLICE else POLICE


def take_role(rt: Any, n: int, log_fn: Any) -> None:
    """Adopt the role sub-game ``n`` owes, before any state is built for it.

    Must run before ``start_sub_game``, which reads the role to pick both
    starting cells and the first mover.
    """
    if not rt.peer.alternate_roles:
        return
    role = role_for(rt.natural_role, n)
    if role != rt.engine.role:
        rt.engine.set_role(role)
        rt.service.my_handshake["role"] = role
        log_fn(f"[{rt.natural_role}] sub-game {n}: playing as {role} (alternating)")


def rehandshake_if_needed(rt: Any, n: int, log_fn: Any) -> bool:
    """Re-negotiate before sub-game ``n`` when the opponent expects it.

    Runs *after* the engine has been reset onto ``n``: a refusal here has to
    record a technical loss for THIS sub-game, and it can only do that against
    freshly-started state. Refusing while the engine still holds sub-game n-1
    files the previous sub-game's ending as this one's result - a capture we
    never played, in a report the lecturer receives.
    """
    if not (rt.peer.handshake_per_sub_game and n > 1):
        return True
    return _rehandshake(rt, n, log_fn)


def _adopt_complementary_role(rt: Any, n: int, theirs: dict[str, Any],
                              payload: dict[str, Any], log_fn: Any) -> None:
    """Take the other side of whatever role they declare, instead of colliding.

    Under alternation the role each peer plays is a function of the sub-game
    index, so once the two indices drift the roles collide on every other
    sub-game and `check_compatibility` turns each one into a technical loss.
    That is unrecoverable by construction: nothing in a refused re-handshake
    ever brings the indices back together. Measured against orcai-mj
    2026-08-13 - their cop went silent for one sub-game and the *whole* series
    died 6/6, twice reporting "both peers claim role 'thief'".

    Joining at their index is already how we start a series (`_join_at_their_index`);
    this is the same principle applied mid-series, and expressed in the only
    term that has to agree for a sub-game to be playable at all - the roles
    being complementary. We re-enter the sub-game so the starting cells match
    the role we just took, exactly as `begin_sub_game` does at a boundary.
    """
    if not rt.peer.alternate_roles:
        return
    their_role = theirs.get("role")
    if their_role not in (POLICE, THIEF) or their_role != rt.engine.role:
        return
    wanted = THIEF if their_role == POLICE else POLICE
    log_fn(f"[{rt.role}] sub-game {n}: they also claim {their_role!r}; taking "
           f"{wanted!r} instead of forfeiting - their index has drifted from ours")
    rt.engine.set_role(wanted)
    rt.engine.begin_sub_game(n)
    rt.service.my_handshake["role"] = wanted
    payload["role"] = wanted


def _rehandshake(rt: Any, n: int, log_fn: Any) -> bool:
    """Exchange a fresh agreement for this sub-game."""
    from ..domain import negotiation
    from .deadline import DeadlineExpiredError

    payload = dict(rt.service.my_handshake)
    payload["sub_game"] = n
    budget = rt.peer.rehandshake_budget_sec
    try:
        theirs = rt.deadline.call_within(
            rt.link.handshake, payload, budget_sec=budget,
            on_retry=lambda err: log_fn(
                f"[{rt.role}] sub-game {n}: re-negotiate failed ({err}); "
                f"retrying up to {budget}s"))
    except DeadlineExpiredError as exc:
        log_fn(f"[{rt.role}] sub-game {n}: opponent never re-negotiated ({exc})")
        rt.engine.declare_technical(rt.engine.other, f"no re-handshake: {exc}")
        return False
    rt.service.their_handshake = theirs
    if theirs.get("agreement_empty"):
        # Silence, not disagreement: their peer answered our request for this
        # index with nothing at all - which is what it does when the index is one
        # it has already settled. Reporting that as a constitution mismatch sends
        # the next hour looking at game.json.
        log_fn(f"[{rt.role}] sub-game {n}: opponent returned an EMPTY agreement "
               f"(no terms, no signature) - it has most likely settled this index "
               f"already; this is silence, not a terms disagreement")
        rt.engine.declare_technical(rt.engine.other, "empty agreement for this sub-game")
        return False
    _adopt_complementary_role(rt, n, theirs, payload, log_fn)
    problems = negotiation.check_compatibility(payload, theirs, num_games=rt.num_games)
    if problems:
        for problem in problems:
            log_fn(f"[{rt.role}] sub-game {n}: REFUSING TO PLAY: {problem}")
        rt.engine.declare_technical(rt.engine.other, f"re-handshake refused: {problems[0]}")
        return False
    return True
