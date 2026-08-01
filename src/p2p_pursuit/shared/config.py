"""Configuration contract: shared signed constitution (JSON) + private peer file (TOML).

``game.json`` holds everything both sides must agree on and is locked by its
canonical SHA-256; ``game.toml`` is private, never crosses the network, and a
shared key always wins over a private one (book Appendix B).
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ..domain.crypto import digest


@dataclass(frozen=True)
class SharedConfig:
    raw: dict[str, Any]
    sha256: str

    @property
    def grid_size(self) -> int:
        return self.raw["board_and_agents"]["grid_size"]

    @property
    def thief_start(self) -> tuple[int, int]:
        return tuple(self.raw["board_and_agents"]["thief_start"])

    @property
    def cop_start(self) -> tuple[int, int]:
        return tuple(self.raw["board_and_agents"]["cop_start"])

    @property
    def first_mover(self) -> str:
        return self.raw["board_and_agents"].get("first_mover", "thief")

    @property
    def map_area(self) -> str:
        return self.raw["world"].get("map_area", "")

    @property
    def hint_max_words(self) -> int:
        return self.raw["world"]["hint_max_words"]

    @property
    def move_set(self) -> list[str]:
        return list(self.raw["movement_and_barriers"]["move_set"])

    @property
    def max_barriers(self) -> int:
        return self.raw["movement_and_barriers"]["max_barriers"]

    @property
    def max_moves(self) -> int:
        return self.raw["movement_and_barriers"]["max_moves"]

    @property
    def survival_threshold(self) -> int:
        return self.raw["movement_and_barriers"]["survival_threshold"]

    @property
    def scoring(self) -> dict[str, int]:
        return self.raw["scoring"]

    @property
    def pheromones(self) -> dict[str, Any]:
        return self.raw["pheromones"]

    @property
    def network(self) -> dict[str, Any]:
        return self.raw["network_and_league"]

    @property
    def num_games(self) -> int:
        return self.raw["network_and_league"]["num_games"]

    @property
    def rate_limiter(self) -> dict[str, Any]:
        return self.raw["rate_limiter_gatekeeper"]


@dataclass(frozen=True)
class PeerConfig:
    raw: dict[str, Any]
    group_name: str = ""
    group_id: str = ""
    members: list[str] = field(default_factory=list)
    repos: dict[str, str] = field(default_factory=dict)
    my_port: int = 8800
    opponent_url: str = ""
    turn_timeout_seconds: int = 180
    strategy: dict[str, str] = field(default_factory=dict)
    trash_talk_provider: str = "template"
    trash_talk_every_n_steps: int = 1
    llm_model: str = ""
    llm_base_url: str = ""
    llm_step_deadline_seconds: int = 30
    email_recipient: str = ""
    email_mode: str = "draft"
    #: Wire + digest contract for this match: "native" or "reference" (RUNBOOK 3b).
    interop_dialect: str = "native"
    #: Swap sides between sub-games (natural role on odd, opposite on even).
    #: Reference-derived peers do this; a fixed-role peer collides with them
    #: from sub-game 2. Negotiated per match, never assumed.
    alternate_roles: bool = False
    #: Re-run the handshake before every sub-game. Reference-derived peers
    #: rebuild their runtime per sub-game and renegotiate; a peer that
    #: handshakes once leaves them waiting until their timeout.
    handshake_per_sub_game: bool = False
    #: Claim a capture when the opponent has no legal move left (book 3.4).
    #: The rule is real, but an unmodified reference peer does not implement it:
    #: it keeps playing, never sends its audit package, and the series desyncs
    #: into role collisions. Measured live 2026-08-01 - see RUNBOOK 3b. So the
    #: claim is a per-opponent negotiation item, exactly like the wire dialect.
    claim_enclosure: bool = True


def load_shared(path: Path) -> SharedConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SharedConfig(raw=raw, sha256=digest(raw))


def load_peer(path: Path) -> PeerConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    game, net = raw.get("game", {}), raw.get("network", {})
    talk, llm, email = raw.get("trash_talk", {}), raw.get("llm", {}), raw.get("email", {})
    interop = raw.get("interop", {})
    return PeerConfig(
        raw=raw,
        group_name=game.get("group_name", ""),
        group_id=game.get("group_id", ""),
        members=list(game.get("members", [])),
        repos=dict(game.get("repos", {})),
        my_port=net.get("my_port", 8800),
        opponent_url=net.get("opponent_url", ""),
        turn_timeout_seconds=net.get("turn_timeout_seconds", 180),
        strategy=dict(raw.get("strategy", {})),
        trash_talk_provider=talk.get("provider", "template"),
        trash_talk_every_n_steps=talk.get("every_n_steps", 1),
        llm_model=llm.get("model", ""),
        llm_base_url=llm.get("base_url", ""),
        llm_step_deadline_seconds=llm.get("step_deadline_seconds", 30),
        email_recipient=email.get("recipient", ""),
        email_mode=email.get("mode", "draft"),
        interop_dialect=interop.get("dialect", "native"),
        alternate_roles=bool(interop.get("alternate_roles", False)),
        handshake_per_sub_game=bool(interop.get("handshake_per_sub_game", False)),
        claim_enclosure=bool(interop.get("claim_enclosure", True)),
    )


#: Cloud hosts hand the port to the process and terminate HTTPS in front of it,
#: so neither value can be pinned in a committed file. ``PORT`` is what Cloud
#: Run / Render / Fly inject; the ``P2P_`` names are explicit overrides for
#: everything else. An exported variable always wins over the TOML, matching how
#: `.env` secrets already behave.
PORT_VARS = ("P2P_MY_PORT", "PORT")
OPPONENT_URL_VAR = "P2P_OPPONENT_URL"
#: The reporting address is a *deployment* decision, not a code one. A hosted
#: rehearsal must be incapable of mailing the lecturer, and the only safe way to
#: guarantee that is to let the environment force `draft` - editing the
#: committed config to run a test invites shipping the edit by accident.
EMAIL_MODE_VAR = "P2P_EMAIL_MODE"
EMAIL_RECIPIENT_VAR = "P2P_EMAIL_RECIPIENT"


def apply_env_overrides(peer: PeerConfig) -> PeerConfig:
    """Overlay the deployment-time values a container cannot know in advance."""
    patch: dict[str, Any] = {}
    for name in PORT_VARS:
        raw = os.environ.get(name)
        if raw and raw.strip().isdigit():
            patch["my_port"] = int(raw.strip())
            break
    url = os.environ.get(OPPONENT_URL_VAR)
    if url and url.strip():
        patch["opponent_url"] = url.strip()
    mode = (os.environ.get(EMAIL_MODE_VAR) or "").strip()
    if mode in ("draft", "send"):
        patch["email_mode"] = mode
    recipient = (os.environ.get(EMAIL_RECIPIENT_VAR) or "").strip()
    if recipient:
        patch["email_recipient"] = recipient
    return replace(peer, **patch) if patch else peer


def load_role(config_dir: Path) -> tuple[SharedConfig, PeerConfig]:
    """Load one role's configuration pair from its private directory."""
    return (load_shared(config_dir / "game.json"),
            apply_env_overrides(load_peer(config_dir / "game.toml")))


def load_rate_limits(config_dir: Path, service: str = "gmail") -> dict[str, Any]:
    """Local Gatekeeper defaults from the versioned rate_limits.json.

    Validates the config version at startup (guidelines 8.1); the shared
    constitution's rate_limiter_gatekeeper section overrides these where the
    two overlap, because agreed values always win over private defaults.
    """
    path = config_dir / "rate_limits.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))["rate_limits"]
    version = raw.get("version", "")
    if not version.startswith("1."):
        raise ValueError(f"rate_limits.json version {version!r} incompatible (need 1.x)")
    services = raw.get("services", {})
    return services.get(service) or services.get("default") or {}


def repo_default_role(root: Path = Path()) -> str | None:
    """Role marker written by the submission split (scripts/sync_repos.py).

    Each published repo carries a one-line ROLE file so `peer` runs with the
    right role by default; the workspace has none, so --role stays explicit.
    """
    path = root / "ROLE"
    if not path.exists():
        return None
    role = path.read_text(encoding="utf-8").strip()
    return role if role in ("police", "thief") else None
