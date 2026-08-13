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
from ..domain.scent import BOOK_V1, MODELS


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
    #: Wall-clock patience for the opening handshake and for each per-sub-game
    #: re-handshake, on top of the short retry burst. An opponent whose peer
    #: bounces behind a healthy tunnel takes every attempt down with it; these
    #: turn that from a technical loss into a pause. Peer-local on purpose - the
    #: constitution is hash-locked, so a knob there would break the handshake.
    handshake_budget_sec: int = 180
    rehandshake_budget_sec: int = 90
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
    #: Serve HTTP without requiring an MCP session handshake. Default ON: a
    #: peer whose client posts tool calls without a session id otherwise gets
    #: 400 and never reaches our engine (measured live, 2026-08-02).
    stateless_http: bool = True
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
    #: Which pheromone physics both sides run: "book_v1" (our reading of book
    #: ch. 4) or "registered_v3" (the inter-team registration - no rounding, no
    #: dust floor, decay+emission in one pinned expression, field served after
    #: the update). A shared model *name* is not a shared physics, so this is
    #: negotiated per opponent and locked before the first move (rule #23).
    scent_model: str = BOOK_V1


#: *Negotiated* terms an opponent may propose differently per match. A
#: reference-derived peer compares the agreed terms for exact equality and
#: refuses to play on any mismatch, so adopting theirs must not mean editing the
#: committed constitution and risking that edit reaching a later match. Each
#: entry is (env var) -> (section, key, caster); `P2P_MAP_AREA` is the original
#: and keeps its name.
MAP_AREA_VAR = "P2P_MAP_AREA"
NEGOTIABLE_TERM_VARS: dict[str, tuple[str, str, Any]] = {
    MAP_AREA_VAR: ("world", "map_area", str),
    # Book rule: a hint is <=15 words. A peer proposing a larger cap is agreeing
    # a ceiling, not an instruction - we still clip our own hints to the book.
    "P2P_HINT_MAX_WORDS": ("world", "hint_max_words", int),
    # Their SmellField's dust floor, which we had modelled as a validation floor
    # under a different value; same physics, so it is theirs to name.
    "P2P_MIN_CENTER_INTENSITY": ("pheromones", "pheromone_min_center_intensity", float),
    # `top_left` vs `top-left`: spelling only, but exact equality does not care.
    "P2P_AXIS_ORIGIN_CORNER": ("board_and_agents", "axis_origin_corner", str),
}


def _shared_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Overlay per-opponent negotiated terms without touching the committed file."""
    for var, (section, key, cast) in NEGOTIABLE_TERM_VARS.items():
        value = (os.environ.get(var) or "").strip()
        if not value:
            continue
        try:
            parsed = cast(value)
        except ValueError:  # a malformed override must not silently mean "default"
            raise ValueError(f"{var}={value!r} is not a valid {cast.__name__}") from None
        raw = {**raw, section: {**raw.get(section, {}), key: parsed}}
    return raw


def load_shared(path: Path) -> SharedConfig:
    raw = _shared_env_overrides(json.loads(path.read_text(encoding="utf-8")))
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
        handshake_budget_sec=net.get("handshake_budget_sec", 180),
        rehandshake_budget_sec=net.get("rehandshake_budget_sec", 90),
        stateless_http=bool(net.get("stateless_http", True)),
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
#: The interop contract is negotiated per opponent, hours before a match, and a
#: hosted peer cannot be rebuilt for each one. These four are exactly the terms
#: RUNBOOK 3b says to settle with every team, so they belong in the environment
#: beside the opponent's URL rather than in a committed file.
DIALECT_VAR = "P2P_DIALECT"
#: The pheromone physics itself is negotiable - see `PeerConfig.scent_model`.
SCENT_MODEL_VAR = "P2P_SCENT_MODEL"
BOOL_VARS = {
    "P2P_ALTERNATE_ROLES": "alternate_roles",
    "P2P_HANDSHAKE_PER_SUB_GAME": "handshake_per_sub_game",
    "P2P_CLAIM_ENCLOSURE": "claim_enclosure",
    "P2P_STATELESS_HTTP": "stateless_http",
}
TRUE, FALSE = ("1", "true", "yes", "on"), ("0", "false", "no", "off")


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
    dialect = (os.environ.get(DIALECT_VAR) or "").strip().lower()
    if dialect in ("native", "reference"):
        patch["interop_dialect"] = dialect
    model = (os.environ.get(SCENT_MODEL_VAR) or "").strip().lower()
    if model:
        if model not in MODELS:
            raise ValueError(f"{SCENT_MODEL_VAR}={model!r} is not one of {MODELS}")
        patch["scent_model"] = model
    for name, field_name in BOOL_VARS.items():
        raw = (os.environ.get(name) or "").strip().lower()
        if raw in TRUE:
            patch[field_name] = True
        elif raw in FALSE:
            patch[field_name] = False
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
