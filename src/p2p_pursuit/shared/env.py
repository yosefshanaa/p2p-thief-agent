"""Minimal .env loader for local secrets (no third-party dependency).

Secrets never live in config/ or in the repo: the API keys used by the
optional banter providers are read from the process environment, and this
loader hydrates that environment from a git-ignored .env for convenience.
An already-exported variable always wins, so CI and shell exports are
authoritative over the file.
"""

from __future__ import annotations

import os
from pathlib import Path


def parse_env(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines; tolerant of comments, quotes and `export`."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1] and len(value) > 1:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()  # inline comment
        out[key] = value
    return out


def load_dotenv(path: Path = Path(".env")) -> int:
    """Load `path` into os.environ without overriding existing values.

    Returns the number of variables actually set (0 when the file is absent,
    which is the normal case in CI and for the zero-token default setup).
    """
    if not path.exists():
        return 0
    set_count = 0
    for key, value in parse_env(path.read_text(encoding="utf-8")).items():
        if key and key not in os.environ:
            os.environ[key] = value
            set_count += 1
    return set_count
