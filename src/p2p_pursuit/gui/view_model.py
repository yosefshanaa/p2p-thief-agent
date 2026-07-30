"""Pure view-model for the live GUI: colors and glyphs from a status snapshot.

Kept free of tkinter so the local-truth invariant and color mapping are unit
testable; the Tk shell only draws what this module computes.
"""

from __future__ import annotations

import math
from typing import Any

from . import theme


def heat_hex(value: float, peak: float) -> str:
    """One posterior cell on the sequential ramp (theme.field_fill)."""
    return theme.field_fill(value, peak)


def scent_radius(value: float) -> float:
    """Trace intensity as a FRACTION OF THE CELL, not a colour.

    The posterior already owns the fill ramp. Scent is a different quantity, so
    it gets a different channel - a disc whose radius grows with intensity -
    and the two can then be read at once instead of fighting for the same cell.
    """
    return max(0.0, min(1.0, value / 0.9)) * 0.26


ROLE_ACCENT = dict(theme.ROLE)


def banner(status: dict[str, Any]) -> tuple[str, str]:
    """(text, color): green when it is our turn, gray once our commit is out;
    at sub-game end the color states the outcome from OUR side of the board."""
    if status.get("end"):
        end = status["end"]
        text = f"{end['ending'].upper()} - winner: {end['winner']}"
        role, winner = status.get("role"), end.get("winner")
        if role and winner in ROLE_ACCENT:
            return text, theme.ASSURE if winner == role else theme.ALARM
        return text, theme.MUTED
    if status.get("my_turn"):
        return "YOUR TURN", theme.ASSURE
    return "COMMITTED", theme.MUTED


SCENT_VISIBLE = 0.05  # below this the trace has decayed past usefulness
GRID_LINE = theme.RULE


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
                cell = {"fill": theme.INK, "text": ""}
            elif (r, c) == own:
                cell = {"fill": ROLE_ACCENT.get(status["role"], theme.ROLE["police"]),
                        "text": status["role"][0].upper()}
            else:
                cell = {"fill": theme.field_fill(belief[r][c], peak), "text": ""}
            cell["belief"] = belief[r][c]
            cell["barrier"] = (r, c) in barriers
            cell["scent"] = scent[r][c] if scent[r][c] > SCENT_VISIBLE else 0.0
            cell["outline"] = GRID_LINE
            cell["width"] = 1
            cell["ring"] = False
            row.append(cell)
        cells.append(row)
    peak_at, _ = belief_stats(belief)
    if belief[peak_at[0]][peak_at[1]] > 0:
        cells[peak_at[0]][peak_at[1]]["ring"] = True
    return cells


def legend_items(role: str = "police") -> list[tuple[str, str]]:
    """Swatch/label pairs for the legend strip under the live board."""
    return [(theme.field_fill(0.7, 1.0), "posterior"),
            (theme.FIELD_HI, "argmax"),
            (theme.TRACE, "trace"),
            (theme.INK, "barrier"),
            (ROLE_ACCENT.get(role, theme.ROLE["police"]), "you")]


def belief_stats(belief: list[list[float]]) -> tuple[tuple[int, int], float]:
    """(argmax cell, Shannon entropy in bits) of the belief heatmap - the two
    numbers the strategy actually steers by (PRD-4), surfaced to the pilot."""
    flat = [(v, (r, c)) for r, row in enumerate(belief) for c, v in enumerate(row)]
    peak_at = max(flat, key=lambda t: t[0])[1]
    total = sum(v for v, _ in flat)
    if total <= 0:
        return peak_at, 0.0
    entropy = -sum((v / total) * math.log2(v / total) for v, _ in flat if v > 0)
    return peak_at, entropy + 0.0  # normalise -0.0, which reads as an error


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


def telemetry_lines(status: dict[str, Any]) -> list[str]:
    """Counters, in the aligned columns an instrument reports them in."""
    return [f"steps    {status['my_steps']:>3} / {status['opp_steps']:<3} opp",
            f"barriers {status['barriers_used']:>3}",
            f"trust    {status['trust']:>5.2f}",
            f"tokens   {status['tokens_used']:>5}"]


def signal_lines(status: dict[str, Any]) -> list[str]:
    """The hint feed as prose, newest last, with direction as a glyph."""
    out = []
    for hint in status.get("hints", []):
        arrow = "sent" if hint.get("dir") == "sent" else "recv"
        out.append(f"{arrow}  {hint.get('hint', '')}")
    return out or ["no hints yet"]
