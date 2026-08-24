"""The per-repository ROLE marker.

The two submission repos are one role-configurable codebase published twice
(book §9.4 / PLAN ADR-2). Each checkout carries a `ROLE` file naming which
agent it is, and that file is the default for `peer --role` there.

Its own module (§3.2) because it is neither a config file nor an environment
variable - it is a property of the checkout.
"""

from __future__ import annotations

from pathlib import Path


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
