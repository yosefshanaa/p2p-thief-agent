"""The Step-0 declaration, and the HMAC proof that authenticates it.

Split out of :mod:`.result_agreement` (§3.2 - split, never compress). One
concern: what we declare before a ball is kicked - both teams, four repo links,
hardware, the code commit that plays (#53), the truthful prior-counted number
(#37) - and the keyed proof a peer checks it with. The end-of-series agreement
stays next door.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from ..domain.crypto import canonical_bytes


def step0_declaration(*, group_id: str, group_name: str, members: list[str],
                      repos: dict[str, str], mcp_endpoint: str, llm_model: str,
                      code_version: str, commit: str,
                      spec: dict[str, Any]) -> dict[str, Any]:
    """Our team subtree in MaRs-777's Step-0 wire shape.

    Four members here are shaped rather than copied, and each was refused by
    their input validation in its natural form:

    * ``github_commits`` is an **object** with both role keys. We run one
      process, so the same hex goes in both - their §7 checks an entry against
      what the contributor declared, never that the two roles differ.
    * ``cpu_freq_ghz`` is canonical decimal **text**, not a JSON number: the
      FastMCP in play turns ``0.10`` into ``Decimal('0.1')``, which moves a
      digest for a reason neither peer can see.
    * ``gpu`` is a non-empty string **or exactly ``false``** - never ``true``,
      and never our own ``"none"``, which their shape accepts as the name of a
      GPU called "none".
    * ``vram_gb`` is **omitted** when there is no GPU, never sent as null.
    """
    gpu = spec.get("gpu") or ""
    has_gpu = bool(gpu) and gpu.lower() not in ("none", "false")
    hardware: dict[str, Any] = {
        "os": spec.get("os", ""),
        "cpu_cores": int(spec.get("cpu_cores") or 0),
        "cpu_freq_ghz": _decimal_text(spec.get("cpu_freq_ghz")),
        "ram_gb": int(spec.get("ram_gb") or 0),
        "gpu": gpu if has_gpu else False,
    }
    if has_gpu and spec.get("vram_gb"):
        hardware["vram_gb"] = int(spec["vram_gb"])
    return {
        "group_id": group_id,
        "group_name": group_name,
        "members": list(members),
        "repos": {"police": repos.get("police") or repos.get("cop") or "",
                  "thief": repos.get("thief") or ""},
        "mcp_endpoint": mcp_endpoint,
        "hardware": hardware,
        "llm_model": llm_model or "none-deterministic-agent",
        "code_version": code_version,
        "github_commits": {"police": commit, "thief": commit},
    }


def _decimal_text(value: Any) -> str:
    """`^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$` - no exponent, no leading zero, no sign
    we did not mean. An unknown frequency is "0", never "" or null, because their
    validator refuses the shape before it reads the meaning."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text or "0"


# -- MaRs-777's HMAC proof (their 18:38 wire) --------------------------------
#: Context bytes prefixed to the canonical document before signing. Two strings,
#: one primitive: a proof minted for one route cannot be replayed on the other,
#: which is the whole reason the prefix exists. No separator and no length
#: prefix - `context + canonical`, concatenated.
CTX_STEP0, CTX_RESULT = b"step0", b"result"

AUTH_PROFILE = "HMAC_SHA256"


def hmac_proof(secret: bytes, context: bytes, document: dict[str, Any]) -> str:
    """``HMAC-SHA256(key, context + canonical(document))``, lowercase hex.

    The key is raw bytes the operator supplies out of band and which never reach
    a config file, a log line or an artifact - see `hmac_secret`.
    """
    import hmac as _hmac

    return _hmac.new(secret, context + canonical_bytes(document), sha256).hexdigest()


def auth_block(secret: bytes, context: bytes, document: dict[str, Any], *,
               key_id: str) -> dict[str, str]:
    """The `auth` object. Only ``key_id`` ever crosses the wire, never the key."""
    return {"profile": AUTH_PROFILE, "key_id": key_id,
            "value": hmac_proof(secret, context, document)}


def step0_core(*, game_id: str, game_uid: str, game_start: str,
               slot: str, declaration: dict[str, Any],
               token_budget_per_series: int) -> dict[str, Any]:
    """The 19 members Step-0's proof covers - NOT the whole declaration.

    Five at the top, nine in our subtree, five in its hardware. Two differences
    from the same subtree as it crosses the wire, and both are theirs:

    * ``cpu_freq_ghz`` is a JSON **number** here and canonical decimal **text**
      on the wire. The same field, two representations, and signing the wire
      form yields a proof that verifies against nothing.
    * ``vram_gb`` is absent from the core even when the wire carries it.
    """
    hardware = dict(declaration.get("hardware") or {})
    hardware.pop("vram_gb", None)
    freq = hardware.get("cpu_freq_ghz")
    hardware["cpu_freq_ghz"] = float(freq) if freq not in (None, "") else 0.0
    subtree = {key: value for key, value in declaration.items() if key != "hardware"}
    subtree["hardware"] = hardware
    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "teams": {slot: subtree},
        "times": {"game_start": game_start},
        "token_budget_per_series": int(token_budget_per_series),
    }
