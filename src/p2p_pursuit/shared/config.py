"""Configuration contract: shared signed constitution (JSON) + private peer file (TOML).

``game.json`` holds everything both sides must agree on and is locked by its
canonical SHA-256; ``game.toml`` is private, never crosses the network, and a
shared key always wins over a private one (book Appendix B).
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain.crypto import digest
from ..domain.scent import BOOK_V1


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
    #: Their endpoint per role they hold, when one URL cannot express it - see
    #: `opponent_url_for`. Empty for every peer that serves both roles at one
    #: address, which is most of them.
    opponent_doors: dict[str, str] = field(default_factory=dict)
    #: *Our* public address per role we hold - the mirror of `opponent_doors`,
    #: and the one an opponent reads back out of our identity block.
    #:
    #: It has to be configured because the process cannot discover it: we bind
    #: `0.0.0.0:<port>` behind a tunnel, so the only address we can derive is a
    #: loopback one that is useless to anybody else. We published exactly that
    #: for months - `{"cop": "http://0.0.0.0:8801/mcp", "thief": same}` - which
    #: is wrong twice over: it is unreachable, and it claims one door for two
    #: roles while we in fact run two processes on two ports. A peer whose
    #: recovery path re-sends its agreement "to the address your identity
    #: declares" (najamjad §3.1) dials nowhere, and reads us as offline.
    #:
    #: Empty falls back to the bind address, which is honest for a local match
    #: and harmless for a peer that never reads the field.
    public_doors: dict[str, str] = field(default_factory=dict)
    turn_timeout_seconds: int = 180
    #: Wall-clock patience for the opening handshake and for each per-sub-game
    #: re-handshake, on top of the short retry burst. An opponent whose peer
    #: bounces behind a healthy tunnel takes every attempt down with it; these
    #: turn that from a technical loss into a pause. Peer-local on purpose - the
    #: constitution is hash-locked, so a knob there would break the handshake.
    #:
    #: Both are negotiable and worth negotiating, because a *mismatch* in
    #: patience is indistinguishable from a broken opponent to whichever side
    #: runs out first - and the shorter side is the one that manufactures the
    #: failure. najamjad hold 1000 s per window and asked us to hold the same.
    handshake_budget_sec: int = 180
    rehandshake_budget_sec: int = 90
    #: How many times a window that abandoned *before it was played* is re-offered
    #: under its own number before the series gives up on it and advances.
    #:
    #: Zero - advance regardless - is what we have always done, and it is wrong
    #: against a peer that re-offers: two peers advancing past unplayed windows
    #: at different rates is how our game 5 meets their game 3 and every window
    #: after that is refused by both guards. najamjad's contract §3.1 requires
    #: the re-offer and reports it ending three series on consecutive evenings.
    #:
    #: Bounded rather than unlimited, because a genuinely dead peer must still
    #: end the series instead of looping on window 1 forever. Per-opponent like
    #: every other interop divergence: a peer that does *not* re-offer would see
    #: our replay of N as a stale duplicate, so this is negotiated, never assumed.
    window_reoffers: int = 0
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
    #: Declare the pursuer's own post-move cell on *every* police turn instead of
    #: letting strategy decide. Our own dialect treats a claim as a disclosure and
    #: spends it deliberately (`claim_threshold`), which is right when the claim is
    #: optional. Some peers specify it as protocol rather than strategy - the cop's
    #: cell, every turn, unsuppressable - and there a withheld claim does not buy
    #: secrecy: the opponent tests co-location only against claims it receives, so
    #: a silent turn spent standing on the thief is a capture forfeited. Negotiated
    #: per opponent, like the dialect. See docs/interop_amireman.md.
    always_claim: bool = False
    #: The `num_games` written into the *signed* terms, when that must differ from
    #: the number of sub-games actually looped. A short compatibility run plays
    #: fewer sub-games by mutual agreement while still signing the full series
    #: length; signing the short count instead fails the peer's terms comparison
    #: on the very run meant to prove the terms agree. `None` signs what is played.
    signed_num_games: int | None = None
    #: Exchange an explicit end-of-series consensus digest after the last
    #: sub-game (amireman §10.3). Off by default: it rides on ``submit_audit``,
    #: and a peer that does not expect it there sees an audit package with no
    #: records - which is how a clean series turns into a technical loss on the
    #: opponent's side. Only enable against a peer whose contract specifies it.
    series_consensus: bool = False
    #: A mutually agreed `game_id` label (e.g. "AHK-DEMO1") replacing the derived
    #: "<lo>-vs-<hi>". Both teams must set the identical string: it is a top-level
    #: key of the consensus object, so a label on one side only guarantees a
    #: digest mismatch at the very end of a series that otherwise played cleanly.
    #: Empty means "derive it", which is the right default for a counted match.
    game_id_label: str = ""
    #: How long to wait for their consensus envelope. Their §10.3 calls the wait
    #: "short and bounded" - failing to receive it costs the confirmation, not
    #: the series, so this must never approach the per-turn deadline.
    consensus_wait_sec: int = 60
    #: How often to re-send our own envelope inside that wait. One unacknowledged
    #: shot into a peer that is not yet listening leaves both sides unsettled with
    #: no mismatch to look at - MaRs-777 resend every 2s for their full window and
    #: require a positive acknowledgement, and they are right to.
    consensus_retry_sec: int = 5
    #: Exchange MaRs-777's `result_agreement` on `receive_control` after the
    #: series, and send a Step-0 declaration at the handshake. Off by default:
    #: both are extensions no other peer we have played speaks, and a Step-0
    #: greeting sent to a peer that does not expect one is refused on shape.
    result_agreement: bool = False
    #: Which serialization the consensus envelope carries - see
    #: `report.consensus.PROJECTIONS`. Negotiated per opponent, because the two
    #: families produce equally plausible 64-hex strings from the same series and
    #: nothing on the wire says which one a peer meant.
    consensus_projection: str = "uid"
    #: Which pheromone physics both sides run: "book_v1" (our reading of book
    #: ch. 4) or "registered_v3" (the inter-team registration - no rounding, no
    #: dust floor, decay+emission in one pinned expression, field served after
    #: the update). A shared model *name* is not a shared physics, so this is
    #: negotiated per opponent and locked before the first move (rule #23).
    scent_model: str = BOOK_V1
    #: Subtractive only: cut the transmitted packet *before* the decay, so our
    #: freshest served centre reads 0.9 instead of 0.8. Not a physics change -
    #: the stored grid is identical either way - but it is what an opponent that
    #: decodes intensity as age actually sees, and reading it the other way puts
    #: a systematic one-step lag on the wire. The kit's document does not settle
    #: which side of the decay the packet comes from, so both readings hash to
    #: the same lock and only a written agreement separates them: s82kma9e's two
    #: golden fields require 0.8 and we filed a counted series under that;
    #: najamjad verify 0.9 on our first transmitted grid and stop at step 1 if
    #: it is not. Hence per opponent, and hence default False.
    scent_serve_before_decay: bool = False


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
        window_reoffers=int(net.get("window_reoffers", 0)),
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
        always_claim=bool(interop.get("always_claim", False)),
        signed_num_games=interop.get("signed_num_games"),
        series_consensus=bool(interop.get("series_consensus", False)),
        game_id_label=str(interop.get("game_id_label", "")),
        consensus_wait_sec=int(interop.get("consensus_wait_sec", 60)),
        consensus_retry_sec=int(interop.get("consensus_retry_sec", 5)),
        consensus_projection=str(interop.get("consensus_projection", "uid")),
        result_agreement=bool(interop.get("result_agreement", False)),
    )


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




# The two pieces of the P2P_* overlay this module applies itself at load time.
# Everything else in `.config_env` is imported directly by whoever needs it,
# rather than re-exported here - a façade would cost this file the size rule.
from .config_env import _shared_env_overrides, apply_env_overrides  # noqa: E402
