"""Step-0 declaration: everything constant for the whole match, hash-signed (#24, #53).

Contents per PRD 4.8: both teams + members, all four repo URLs, both MCP
addresses, hardware, LLM model, agreed token cap, code version, the git
commit being played, game number and start time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..shared import sysinfo
from ..shared.version import CODE_VERSION
from .crypto import digest


def team_block(
    *, group_id: str, group_name: str, members: list[str], repos: dict[str, str],
    mcp_url: str, llm_model: str,
) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "group_name": group_name,
        "members": members,
        "repos": repos,
        "mcp_url": mcp_url,
        "llm_model": llm_model or "template (no LLM)",
        "hardware": sysinfo.collect(),
        "code_version": CODE_VERSION,
        "github_commit": sysinfo.git_commit(),
    }


def build_declaration(
    *, game_uid: str, game_id: str, game_number: int, config_sha256: str,
    scent_model_sha256: str, token_cap: int, me: dict[str, Any],
    opponent: dict[str, Any] | None,
) -> dict[str, Any]:
    body = {
        "report_type": "declaration",
        "game_uid": game_uid,
        "game_id": game_id,
        "game_number": game_number,
        "config_sha256": config_sha256,
        "scent_model_sha256": scent_model_sha256,
        "token_cap": token_cap,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ended_at": None,
        "teams": {"mine": me, "opponent": opponent},
    }
    body["declaration_sha256"] = digest(dict(body))
    return body


def close_declaration(declaration: dict[str, Any],
                      ended_at: str | None = None) -> dict[str, Any]:
    """Stamp the finish time onto a declaration and re-seal it.

    ``ended_at`` was a field the builder set to ``None`` and nothing ever wrote
    back, so every filed declaration - the artifact the lecturer receives -
    claimed a start and no end, and the only end time in the whole match lived
    in a different file. The hash is recomputed over the same rule the builder
    uses (everything except the key itself), or the re-stamped document would
    fail its own integrity check.
    """
    body = {key: value for key, value in declaration.items()
            if key != "declaration_sha256"}
    body["ended_at"] = ended_at or datetime.now(UTC).isoformat(timespec="seconds")
    body["declaration_sha256"] = digest(dict(body))
    return body
