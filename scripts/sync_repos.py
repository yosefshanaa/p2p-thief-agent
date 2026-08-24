"""Two-repo submission sync: workspace -> p2p-police-agent / p2p-thief-agent.

Book §9.4 / PLAN ADR-2: one role-configurable codebase, published as two
self-contained plain-tree repos (no submodules - the grader must see files).
Only git-tracked workspace files are copied, so secrets / logs / results can
never leak by construction. Per-repo deltas: a ROLE marker (picked up by the
CLI as the default `peer --role`) and a README role banner + sister link.

Usage:  uv run python scripts/sync_repos.py [--push]
Repo names/owner/paths come from config/repos.toml - nothing hard-coded.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
SECRETS = ("credentials.json", "token.json", ".env")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          capture_output=True).stdout


def tracked_files(workspace: Path) -> list[str]:
    """Everything git tracks - by construction excludes ignored secrets."""
    return [f for f in _git(workspace, "ls-files").splitlines() if f]


def role_banner(role: str, urls: dict[str, str]) -> str:
    """Role line + the provenance line pointing back at the development repo.

    Both are regenerated from the pristine workspace README on every sync, so
    editing them in a published repo is pointless - the next run overwrites it.
    """
    sister = "thief" if role == "police" else "police"
    return (f"> **Role of this repository: {role.upper()} agent** — "
            f"`uv run p2p-pursuit peer` defaults to `--role {role}` here "
            f"(`ROLE` marker). Sister ({sister}) repository: {urls[sister]}\n"
            f">\n"
            f"> **Developed in [`{urls['workspace_name']}`]({urls['workspace']})** — "
            f"the single role-configurable codebase both agents are built from, "
            f"carrying the full commit history and the league match archive. This "
            f"repository is published from it by `scripts/sync_repos.py`.\n")


def transform_readme(text: str, role: str, urls: dict[str, str]) -> str:
    """Insert the role banner right under the H1; idempotent."""
    lines = text.splitlines(keepends=True)
    if len(lines) > 2 and lines[2].startswith("> **Role of this"):
        return text
    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        if i == 0 and line.startswith("# "):
            out.extend(["\n", role_banner(role, urls)])
    return "".join(out)


def sync_one(workspace: Path, target: Path, role: str, urls: dict[str, str]) -> int:
    """Mirror the tracked tree into target (keeps target/.git), apply deltas."""
    for item in target.iterdir():
        if item.name == ".git":
            continue
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    files = tracked_files(workspace)
    for rel in files:
        src, dst = workspace / rel, target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (target / "ROLE").write_text(role + "\n", encoding="utf-8")
    readme = target / "README.md"
    readme.write_text(
        transform_readme(readme.read_text(encoding="utf-8"), role, urls),
        encoding="utf-8")
    return len(files)


def secrets_history_clean(repo: Path) -> bool:
    """Guardrail: no secret file was EVER added in any commit of `repo`."""
    out = _git(repo, "log", "--all", "--diff-filter=A", "--format=%H", "--", *SECRETS)
    return out.strip() == ""


def _publish(target: Path, subject: str, push: bool) -> None:
    _git(target, "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=target).returncode:
        _git(target, "commit", "-m", subject)
    if not secrets_history_clean(target):
        sys.exit(f"FATAL: secret file present in {target} history - do NOT push")
    if push:
        _git(target, "push", "-u", "origin", "HEAD")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--push", action="store_true", help="commit AND push both repos")
    args = ap.parse_args(argv)
    cfg = tomllib.loads((WORKSPACE / "config" / "repos.toml").read_text("utf-8"))["sync"]
    urls = {r: f"https://github.com/{cfg['owner']}/{name}"
            for r, name in cfg["roles"].items()}
    urls["workspace_name"] = cfg["workspace"]
    urls["workspace"] = f"https://github.com/{cfg['owner']}/{cfg['workspace']}"
    head = _git(WORKSPACE, "log", "-1", "--format=%h %s").strip()
    for role, name in cfg["roles"].items():
        target = (WORKSPACE / cfg["repos_root"] / name).resolve()
        if not (target / ".git").is_dir():
            sys.exit(f"FATAL: {target} is not a git clone - create it first")
        n = sync_one(WORKSPACE, target, role, urls)
        _publish(target, f"sync: workspace {head}", args.push)
        print(f"[sync] {role}: {n} files -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
