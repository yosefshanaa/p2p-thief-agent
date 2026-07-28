"""Host hardware specification for the step-0 declaration (book ch. 5.5)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess


def _ram_gb() -> float | str:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return "unknown"


def _gpu() -> str:
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            pass
    return "none"


def git_commit() -> str:
    """The commit hash actually being played - mandatory in every declaration (#53)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def collect() -> dict:
    return {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_cores": os.cpu_count() or 0,
        "ram_gb": _ram_gb(),
        "gpu": _gpu(),
    }
