"""Host hardware specification for the step-0 declaration (book ch. 5.5)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


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
        "cpu_freq_ghz": _cpu_freq_ghz(),
        "gpu": _gpu(),
    }


def _cpu_freq_ghz() -> float:
    """Nominal core frequency in GHz, 0.0 when it cannot be read.

    MaRs-777's Step-0 requires it, as canonical decimal *text* rather than a
    JSON number - see `report.result_agreement.step0_declaration`. Read from
    /proc rather than a dependency, and never raising: a declaration that cannot
    be built is a match that cannot start, and an unknown frequency is a
    cosmetic gap in an artifact.
    """
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("cpu mhz"):
                return round(float(line.split(":", 1)[1].strip()) / 1000.0, 2)
    except (OSError, ValueError, IndexError):
        pass
    try:
        raw = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
        return round(int(raw.read_text().strip()) / 1_000_000.0, 2)
    except (OSError, ValueError):
        return 0.0
