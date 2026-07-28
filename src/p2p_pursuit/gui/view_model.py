"""Pure view-model for the live GUI: colors and glyphs from a status snapshot.

Kept free of tkinter so the local-truth invariant and color mapping are unit
testable; the Tk shell only draws what this module computes.
"""

from __future__ import annotations

import math
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


SCENT_VISIBLE = 0.05  # below this the trace has decayed past usefulness
GRID_LINE = "#cccccc"


def board_cells(status: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """Per-cell render info. Contains ONLY local truth (#8-9): belief, the
    opponent's SERVED scent field (our observation), declared barriers and our
    own position - never the opponent's cell."""
    n = status["board_size"]
    belief = status["belief"]
    peak = max(max(row) for row in belief) or 1.0
    scent = status.get("opp_scent") or [[0.0] * n for _ in range(n)]
    barriers = {tuple(b) for b in status["barriers"]}
    own = tuple(status["own_pos"])
    cells = []
    for r in range(n):
        row = []
        for c in range(n):
            if (r, c) in barriers:
                cell = {"fill": "#222222", "text": "#"}
            elif (r, c) == own:
                cell = {"fill": "#2266dd", "text": status["role"][0].upper()}
            else:
                cell = {"fill": heat_hex(belief[r][c], peak), "text": ""}
            scented = cell["text"] == "" and scent[r][c] > SCENT_VISIBLE
            cell["outline"] = scent_hex(scent[r][c]) if scented else GRID_LINE
            cell["width"] = 3 if scented else 1
            cell["ring"] = False
            row.append(cell)
        cells.append(row)
    peak_at, _ = belief_stats(belief)
    if belief[peak_at[0]][peak_at[1]] > 0:
        cells[peak_at[0]][peak_at[1]]["ring"] = True
    return cells


def belief_stats(belief: list[list[float]]) -> tuple[tuple[int, int], float]:
    """(argmax cell, Shannon entropy in bits) of the belief heatmap - the two
    numbers the strategy actually steers by (PRD-4), surfaced to the pilot."""
    flat = [(v, (r, c)) for r, row in enumerate(belief) for c, v in enumerate(row)]
    peak_at = max(flat, key=lambda t: t[0])[1]
    total = sum(v for v, _ in flat)
    if total <= 0:
        return peak_at, 0.0
    entropy = -sum((v / total) * math.log2(v / total) for v, _ in flat if v > 0)
    return peak_at, entropy


def info_lines(status: dict[str, Any]) -> list[str]:
    """The side panel's full text, composed away from tkinter so it is
    unit-testable (and identical between live view and future frontends)."""
    peak_at, entropy = belief_stats(status["belief"])
    lines = [f"role: {status['role']}   sub-game: {status['sub_game']}",
             f"phase: {status['phase']}",
             f"my steps: {status['my_steps']}   opp steps: {status['opp_steps']}",
             f"barriers used: {status['barriers_used']}",
             f"hint trust: {status['trust']:.2f}   tokens: {status['tokens_used']}",
             f"belief peak @ {peak_at}   entropy {entropy:.2f} bits", ""]
    lines += [f"[{h['dir']}] {h['hint']}" for h in status.get("hints", [])]
    if status.get("end"):
        lines += ["", f"END: {status['end']['ending']}"]
    return lines
