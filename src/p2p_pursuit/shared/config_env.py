"""The deployment-time environment overlay: every P2P_* variable, in one place.

Split out of :mod:`.config` (§3.2 - split, never compress). One concern: values
a committed config file cannot know - the port this container got, the
opponent's URL and per-role doors, the negotiated per-opponent terms, and the
HMAC secret, which is read from the environment and never from a file that
could reach a repository.

The overlay is applied *after* loading, so the committed constitution stays the
thing both peers hashed. `config_sha256` is taken from the file, not from this.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..domain.scent import MODELS

if TYPE_CHECKING:  # runtime import would cycle: config imports this module
    from .config import PeerConfig


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


#: Cloud hosts hand the port to the process and terminate HTTPS in front of it,
#: so neither value can be pinned in a committed file. ``PORT`` is what Cloud
#: Run / Render / Fly inject; the ``P2P_`` names are explicit overrides for
#: everything else. An exported variable always wins over the TOML, matching how
#: `.env` secrets already behave.
PORT_VARS = ("P2P_MY_PORT", "PORT")
OPPONENT_URL_VAR = "P2P_OPPONENT_URL"
#: A door per role, for a peer that runs one OS process per role on addresses a
#: `{role}` substitution cannot build - two ports, two hosts, two schemes. Keyed
#: by the role *they* hold, spelled their way, because that is how their own
#: pairing message names the endpoints. Either may be set alone; whichever is
#: missing falls back to `P2P_OPPONENT_URL`.
OPPONENT_DOOR_VARS = {"police": "P2P_OPPONENT_COP_URL",
                      "thief": "P2P_OPPONENT_THIEF_URL"}
#: The same, for the doors *we* serve - see `PeerConfig.public_doors`. Keyed by
#: the role we hold and spelled their way, so the identity block we publish
#: reads `{"cop": ..., "thief": ...}` whatever we call the roles internally.
#: In the environment rather than a committed file for the same reason as the
#: opponent's: a quick tunnel's hostname is minted minutes before a match.
PUBLIC_DOOR_VARS = {"police": "P2P_PUBLIC_COP_URL",
                    "thief": "P2P_PUBLIC_THIEF_URL"}
#: Some peers serve one agent per role on one port (`/cop/mcp`, `/thief/mcp`)
#: rather than one endpoint that routes. Against those, the endpoint we must push
#: to is a function of the sub-game: under alternation their cop plays the even
#: sub-games and their thief the odd ones, so a link pinned at one of the two
#: spends half a series talking to an idle agent. Writing `{role}` in the URL
#: says "substitute THEIR role for the sub-game about to be played" - measured
#: against gal-roy1, whose `/mcp` root is not mounted at all.
ROLE_PLACEHOLDER = "{role}"
#: The reference family spells our `police` as `cop` - it is the key their own
#: identity block uses (`interop_codec.interop_identity`: `mcp_servers` is keyed
#: cop/thief), and it is the path segment gal-roy1 actually serves. Substituting
#: our own spelling would ask for `/police/mcp` and get a 404, so the placeholder
#: is defined in *their* vocabulary. A peer that serves some third spelling needs
#: its own entry here rather than a hand-edited URL, because the substitution has
#: to happen again at every alternation boundary.
WIRE_ROLE_NAMES = {"police": "cop", "thief": "thief"}


def opponent_url_for(url: str, their_role: str,
                     doors: dict[str, str] | None = None) -> str:
    """Their endpoint for a sub-game in which they hold ``their_role``.

    Three topologies, because three are in use. One URL serving both roles is
    the common case and needs nothing. gal-roy1 serves a path per role and said
    so with `{role}`, which is a substitution. vibecode runs two OS processes on
    two *ports* of one host (Appendix E rule 1), and a port cannot be built by
    substituting a role name - `:6122{role}` yields `:6122cop`. So a peer may
    also name its doors outright, which covers any split at all: different port,
    different host, different scheme.
    """
    if doors:
        door = doors.get(their_role)
        if door:
            return door
    if ROLE_PLACEHOLDER not in url:
        return url
    return url.replace(ROLE_PLACEHOLDER, WIRE_ROLE_NAMES.get(their_role, their_role))
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
#: So is the consensus serialization - see `PeerConfig.consensus_projection`.
CONSENSUS_PROJECTION_VAR = "P2P_CONSENSUS_PROJECTION"
BOOL_VARS = {
    "P2P_ALTERNATE_ROLES": "alternate_roles",
    "P2P_HANDSHAKE_PER_SUB_GAME": "handshake_per_sub_game",
    "P2P_CLAIM_ENCLOSURE": "claim_enclosure",
    "P2P_ALWAYS_CLAIM": "always_claim",
    "P2P_SERIES_CONSENSUS": "series_consensus",
    "P2P_RESULT_AGREEMENT": "result_agreement",
    "P2P_STATELESS_HTTP": "stateless_http",
    "P2P_SCENT_SERVE_BEFORE_DECAY": "scent_serve_before_decay",
}
#: The banter provider, per match. An LLM call carries a deadline of its own and
#: can push a single turn against an opponent's per-turn envelope - najamjad
#: expire a turn at 30 s. Promising a peer we will run the zero-token template
#: has to be expressible without editing the committed `game.toml`, because that
#: edit would ride silently into the next opponent's match.
TRASH_TALK_VAR = "P2P_TRASH_TALK_PROVIDER"
#: The brain class for a role, per match. Same reasoning as the banter provider
#: and more so: swapping a brain by editing the committed `[strategy]` section
#: would ride silently into every later opponent, and a brain that calls out to
#: a model is exactly the kind of thing that must be armed for one match only.
BRAIN_CLASS_VARS = {"P2P_POLICE_CLASS": "police_class",
                    "P2P_THIEF_CLASS": "thief_class"}
#: Numeric peer-local knobs settled per opponent, hours before a match. None of
#: them is hashed, so an opponent can ask us to move one without re-signing the
#: constitution - which is exactly what `handshake_budget_sec` is for.
INT_VARS = {
    "P2P_TURN_TIMEOUT": "turn_timeout_seconds",
    "P2P_HANDSHAKE_BUDGET": "handshake_budget_sec",
    "P2P_REHANDSHAKE_BUDGET": "rehandshake_budget_sec",
    "P2P_WINDOW_REOFFERS": "window_reoffers",
}
#: Signed series length, when a short run must still sign the full one.
SIGNED_NUM_GAMES_VAR = "P2P_SIGNED_NUM_GAMES"
#: A mutually agreed `game_id` label, replacing the derived "<lo>-vs-<hi>".
GAME_ID_LABEL_VAR = "P2P_GAME_ID"
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
    doors = {role: (os.environ.get(var) or "").strip()
             for role, var in OPPONENT_DOOR_VARS.items()}
    doors = {role: door for role, door in doors.items() if door}
    if doors:
        patch["opponent_doors"] = doors
    mine = {role: (os.environ.get(var) or "").strip()
            for role, var in PUBLIC_DOOR_VARS.items()}
    mine = {role: door for role, door in mine.items() if door}
    if mine:
        patch["public_doors"] = mine
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
    projection = (os.environ.get(CONSENSUS_PROJECTION_VAR) or "").strip().lower()
    if projection:
        from ..report.consensus import PROJECTIONS
        if projection not in PROJECTIONS:
            raise ValueError(f"{CONSENSUS_PROJECTION_VAR}={projection!r} is not "
                             f"one of {PROJECTIONS}")
        patch["consensus_projection"] = projection
    talk = (os.environ.get(TRASH_TALK_VAR) or "").strip().lower()
    if talk:
        patch["trash_talk_provider"] = talk
    brains = {key: (os.environ.get(var) or "").strip()
              for var, key in BRAIN_CLASS_VARS.items()}
    brains = {key: spec for key, spec in brains.items() if spec}
    if brains:
        patch["strategy"] = {**peer.strategy, **brains}
    label = (os.environ.get(GAME_ID_LABEL_VAR) or "").strip()
    if label:
        patch["game_id_label"] = label
    signed = (os.environ.get(SIGNED_NUM_GAMES_VAR) or "").strip()
    if signed:
        if not signed.isdigit() or int(signed) < 1:
            raise ValueError(f"{SIGNED_NUM_GAMES_VAR}={signed!r} is not a positive integer")
        patch["signed_num_games"] = int(signed)
    for name, field_name in BOOL_VARS.items():
        raw = (os.environ.get(name) or "").strip().lower()
        if raw in TRUE:
            patch[field_name] = True
        elif raw in FALSE:
            patch[field_name] = False
    for name, field_name in INT_VARS.items():
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            continue
        # Loudly, not silently: a patience knob that a typo turned back into its
        # default is the failure it exists to prevent, and it would only show up
        # as an unexplained technical loss mid-series.
        if not raw.isdigit():
            raise ValueError(f"{name}={raw!r} is not a non-negative integer")
        patch[field_name] = int(raw)
    return replace(peer, **patch) if patch else peer


#: MaRs-777's HMAC key id - public, and the only half that crosses the wire.
HMAC_KEY_ID_VAR = "P2P_HMAC_KEY_ID"
#: The shared secret itself. **Environment only, and only from `.env`.** Never a
#: config file, never a log line, never an artifact: a secret committed once is
#: a secret forever, and `config/opponents/*.env` is tracked.
HMAC_SECRET_VAR = "P2P_HMAC_SECRET"


def hmac_secret() -> bytes | None:
    """The shared secret as its own **UTF-8 bytes**, or None when unconfigured.

    **Never hex-decoded, whatever it looks like.** A 64-character hex secret is a
    64-byte key here, not the 32 bytes it would decode to, and the two derivations
    produce completely different HMACs from identical inputs. We shipped the
    decoding version for about ten minutes on 2026-08-24 and it agreed with
    nothing; MaRs-777 published two vectors computed the same wrong way and had to
    void them. Their production is `AuthSecret(env[...].encode())` and ours is
    this, and the only reason either side knows is that both published a vector.

    Never logged or echoed - the caller gets bytes or nothing, and any message
    about it names the variable rather than a value.
    """
    raw = (os.environ.get(HMAC_SECRET_VAR) or "").strip()
    return raw.encode("utf-8") if raw else None


def hmac_fingerprint(secret: bytes) -> str:
    """``sha256(secret_text)[:16]`` - their published check value.

    Safe to print: it is a one-way digest they publish themselves, and it is how
    both sides confirm they hold the same key without either sending it.
    """
    from hashlib import sha256

    return sha256(secret).hexdigest()[:16]
