"""Logging bootstrap from the versioned config/logging_config.json.

Game telemetry stays in the sealed JSON logs; this configures the Python
logging tree (uvicorn/FastMCP included) so infrastructure noise has one
switch. stdout is never touched - it stays machine-readable JSON only.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


def configure(config_path: Path = Path("config/logging_config.json")) -> None:
    level, fmt = "INFO", "%(asctime)s %(name)s %(levelname)s %(message)s"
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        level = raw.get("level", level)
        fmt = raw.get("format", fmt)
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format=fmt, stream=sys.stderr, force=True)
