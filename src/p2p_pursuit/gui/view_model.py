"""Pure view-model for the live GUI: colors and glyphs from a status snapshot.

Kept free of tkinter so the local-truth invariant and color mapping are unit
testable; the Tk shell only draws what this module computes.
"""

from __future__ import annotations

from typing import Any


def heat_hex(value: float, peak: float) -> str:
    """Belief heat: white -> deep red as probability approaches the current peak."""
    if peak <= 0:
        return "#ffffff"
    x = max(0.0, min(1.0, value / peak))
    g_b = int(255 * (1.0 - x * 0.85))
    return f"#ff{g_b:02x}{g_b:02x}"


def scent_hex(value: float) -> str:
    """Opponent scent overlay: white -> deep violet with intensity."""
    x = max(0.0, min(1.0, value / 0.9))
    g = int(255 * (1.0 - x * 0.75))
    return f"#{g:02x}{g:02x}ff"


def banner(status: dict[str, Any]) -> tuple[str, str]:
    """(text, color): green when it is our turn, gray once our commit is out."""
    if status.get("end"):
        end = status["end"]
        return f"{end['ending'].upper()} - winner: {end['winner']}", "#4488ff"
    if status.get("my_turn"):
        return "YOUR TURN", "#22aa44"
    return "LOCKED", "#888888"


def board_cells(status: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """Per-cell render info. Contains ONLY local truth (#8-9): belief, own scent
    echo, declared barriers and our own position - never the opponent's cell."""
    n = status["board_size"]
    belief = status["belief"]
    peak = max(max(row) for row in belief) or 1.0
    barriers = {tuple(b) for b in status["barriers"]}
    own = tuple(status["own_pos"])
    cells = []
    for r in range(n):
        row = []
        for c in range(n):
            if (r, c) in barriers:
                row.append({"fill": "#222222", "text": "#"})
            elif (r, c) == own:
                row.append({"fill": "#2266dd", "text": status["role"][0].upper()})
            else:
                row.append({"fill": heat_hex(belief[r][c], peak), "text": ""})
        cells.append(row)
    return cells
