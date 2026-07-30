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


def prepare_sub_game(rt: Any, n: int, log_fn: Any) -> bool:
    """Swap sides and/or re-handshake before sub-game ``n``; False = cannot play."""
    if rt.peer.alternate_roles:
        role = role_for(rt.natural_role, n)
        if role != rt.engine.role:
            rt.engine.set_role(role)
            rt.service.my_handshake["role"] = role
            log_fn(f"[{rt.natural_role}] sub-game {n}: playing as {role} (alternating)")
    if rt.peer.handshake_per_sub_game and n > 1:
        return _rehandshake(rt, n, log_fn)
    return True


def _rehandshake(rt: Any, n: int, log_fn: Any) -> bool:
    """Exchange a fresh agreement for this sub-game."""
    from ..domain import negotiation
    from .deadline import DeadlineExpiredError

    payload = dict(rt.service.my_handshake)
    payload["sub_game"] = n
    try:
        theirs = rt.deadline.call(rt.link.handshake, payload)
    except DeadlineExpiredError as exc:
        log_fn(f"[{rt.role}] sub-game {n}: opponent never re-negotiated ({exc})")
        rt.engine.declare_technical(rt.engine.other, f"no re-handshake: {exc}")
        return False
    rt.service.their_handshake = theirs
    problems = negotiation.check_compatibility(payload, theirs, num_games=rt.num_games)
    if problems:
        for problem in problems:
            log_fn(f"[{rt.role}] sub-game {n}: REFUSING TO PLAY: {problem}")
        rt.engine.declare_technical(rt.engine.other, f"re-handshake refused: {problems[0]}")
        return False
    return True
