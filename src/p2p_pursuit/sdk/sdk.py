"""PursuitSDK - the single business-logic entry point (guidelines ch. 4).

Every consumer (CLI, GUI, tests, future REST/third parties) calls this
facade; no external layer reaches into domain/peer/infra modules directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..domain.rules import POLICE


class PursuitSDK:
    """Facade over the peer runtime, the local tactics lab, replay and reporting."""

    # -- networked peer -------------------------------------------------------
    def create_peer(self, role: str, config_dir: Path | None = None, *,
                    out_dir: Path = Path("results"), seed: int | None = None,
                    counted: bool = False, prior_counted_games: int = 0,
                    num_games: int | None = None):
        from ..peer.runtime import PeerRuntime

        return PeerRuntime(role, config_dir or Path(f"config/{role}"), out_dir=out_dir,
                           seed=seed, counted=counted,
                           prior_counted_games=prior_counted_games, num_games=num_games)

    def make_link(self, url: str):
        from ..infra.mcp_client import McpLink

        return McpLink(url)

    # -- in-process series (tactics lab / demo) -------------------------------
    def run_local_series(self, *, police_dir: Path = Path("config/police"),
                         thief_dir: Path = Path("config/thief"),
                         num_games: int | None = None, seed: int | None = None,
                         on_sub_game: Any = None):
        from ..peer.local_match import run_series
        from ..shared.config import load_role

        shared, police_cfg = load_role(police_dir)
        _, thief_cfg = load_role(thief_dir)
        series = run_series(shared, police_cfg, thief_cfg, num_games=num_games,
                            seed=seed, on_sub_game=on_sub_game)
        return shared, police_cfg, thief_cfg, series

    # -- replay & verification -------------------------------------------------
    def load_replay(self, log_path: Path) -> dict[str, Any]:
        from ..gui.replay_data import load_log, timeline, verdict_of

        log = load_log(log_path)
        verdict, mine, theirs = verdict_of(log)
        return {"log": log, "verdict": verdict, "timeline": timeline(log),
                "records_checked": len(mine) + len(theirs)}

    def audit_binding(self, match_dir: Path) -> dict[str, Any]:
        """Re-check every sealed log in a match directory for commit binding.

        The offline form of the promise both peers make to each other: every
        commitment sent during a sub-game is revealed afterwards as the exact
        (payload, nonce) that produced it, and nothing from a neighbouring
        sub-game is mixed in. Runs from the artifacts alone - no engine, no
        network, either team's copy.
        """
        import json

        from ..infra.interop_audit import audit_sealed_log

        rows = [audit_sealed_log(json.loads(path.read_text(encoding="utf-8")))
                for path in sorted(match_dir.glob("log_*.json"))]
        return {
            "match_dir": str(match_dir),
            "sub_games": rows,
            "mine_binds": all(row["mine_binds"] for row in rows),
            "theirs_binds": all(row["theirs_binds"] for row in rows),
            "reveals_received": sum(row["their_reveal_received"] for row in rows),
        }

    # -- reporting -------------------------------------------------------------
    def build_local_result(self, *, game_uid: str, game_id: str, shared: Any,
                           police_cfg: Any, sub_games: list[dict[str, Any]],
                           police_total: int, thief_total: int,
                           tokens_used: int) -> dict[str, Any]:
        from ..report import results
        from ..shared import sysinfo

        return results.build_result(
            game_uid=game_uid, game_id=game_id,
            my_group={"group_id": police_cfg.group_id, "members": police_cfg.members,
                      "repos": police_cfg.repos},
            opp_group=None, sub_games=sub_games, police_total=police_total,
            thief_total=thief_total, tie_score=shared.scoring.get("tie_score", 2),
            tokens_used=tokens_used, github_commit=sysinfo.git_commit(),
            my_role=POLICE,
            mutual_agreement=results.agreement_reached(sub_games))

    #: Cloud Run mounts one secret per directory, so a hosted peer cannot have
    #: token.json and credentials.json sitting side by side in /app. The paths
    #: therefore have to be addressable, like the port and the opponent URL.
    TOKEN_PATH_VAR = "P2P_GMAIL_TOKEN"
    CREDENTIALS_PATH_VAR = "P2P_GMAIL_CREDENTIALS"

    @classmethod
    def gmail_paths(cls) -> tuple[Path, Path]:
        """(credentials, token), overridable for a mounted deployment."""
        import os

        return (Path(os.environ.get(cls.CREDENTIALS_PATH_VAR) or "credentials.json"),
                Path(os.environ.get(cls.TOKEN_PATH_VAR) or "token.json"))

    def pick_email_transport(self, mode: str, notify: Any = print):
        from ..infra.email_sender import DryRunTransport

        credentials, token = self.gmail_paths()
        if mode != "send":
            notify(f"[email] mode={mode!r}: dry-run (send-only scope has no drafts)")
        elif token.exists():
            try:
                from ..infra.email_sender import GmailTransport

                return GmailTransport(credentials, token)
            except Exception as exc:  # noqa: BLE001 - fall back, never crash a report
                notify(f"[email] Gmail unavailable ({exc}); dry-run transport")
        else:
            notify(f"[email] no token at {token}; dry-run (report written, not sent)")
        return DryRunTransport()

    def authorize_gmail(self, credentials: Path = Path("credentials.json"),
                        token: Path = Path("token.json")) -> str:
        from ..infra.email_sender import run_authorization

        return run_authorization(credentials, token)

    # -- diagnostics -------------------------------------------------------------
    def smoke(self, url: str, timeout: float = 10) -> dict[str, Any]:
        """Probe a peer: reachability, advertised tools and which dialect they speak.

        Liveness is decided by the tool listing, not by our ``health_check``:
        a reference-derived peer has no such tool and would otherwise read as
        dead while it is perfectly ready to play.
        """
        from ..infra import dialect
        from ..infra.transport import LinkError

        link, error, tools = self.make_link(url), None, []
        try:
            tools = sorted(link.list_tools(timeout=timeout))
        except LinkError as exc:
            error = str(exc)
        name = dialect.classify(tools)
        health: dict[str, Any] = {}
        if "health_check" in tools:
            try:
                health = link.health(timeout=timeout)
            except LinkError as exc:
                error = str(exc)
        return {"reachable": bool(tools), "dialect": name,
                "guidance": dialect.describe(name), "tools": tools,
                "health": health, "error": error}
