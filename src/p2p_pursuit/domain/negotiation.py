"""Pre-game handshake: identity, constitution lock, scent-model lock, first mover.

Both peers must load a byte-identical constitution (#11) and the same scent
model (#23); any mismatch refuses the game before move 1. Counted matches
must play the binding 6 sub-games (Appendix F), guarding against demo configs.
"""

from __future__ import annotations

from typing import Any

from ..shared.config import PeerConfig, SharedConfig
from ..shared.version import CODE_VERSION
from .crypto import digest
from .scent import scent_model_document

BINDING_SUB_GAMES = 6


def scent_model_sha256() -> str:
    return digest(scent_model_document())


def handshake_payload(shared: SharedConfig, peer: PeerConfig, *, role: str,
                      game_id: str, game_uid: str, counted: bool,
                      prior_counted_games: int) -> dict[str, Any]:
    return {
        "kind": "handshake",
        "role": role,
        "group_id": peer.group_id,
        "group_name": peer.group_name,
        "members": peer.members,
        "repos": peer.repos,
        "code_version": CODE_VERSION,
        "config_sha256": shared.sha256,
        "scent_model_sha256": scent_model_sha256(),
        "first_mover": shared.first_mover,
        "game_id": game_id,
        "game_uid": game_uid,
        "counted": counted,
        "prior_counted_games": prior_counted_games,  # truthful declaration, rule #37
    }


def check_compatibility(mine: dict[str, Any], theirs: dict[str, Any],
                        *, num_games: int) -> list[str]:
    """Return every reason NOT to play; empty list means the game may start."""
    problems: list[str] = []
    if theirs.get("config_sha256") != mine["config_sha256"]:
        problems.append("constitution mismatch: game.json is not byte-identical (#11)")
    if theirs.get("scent_model_sha256") != mine["scent_model_sha256"]:
        problems.append("scent model mismatch: emission/decay lock differs (#23)")
    if theirs.get("first_mover") != mine["first_mover"]:
        problems.append("first-mover disagreement")
    if theirs.get("role") == mine["role"]:
        problems.append(f"both peers claim role {mine['role']!r}")
    if mine.get("counted") and num_games != BINDING_SUB_GAMES:
        problems.append(f"counted match requires {BINDING_SUB_GAMES} sub-games, not {num_games}")
    return problems
