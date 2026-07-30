"""Live viewer: this agent's posterior over an opponent it cannot see.

Local truth only (book 7.3, rules #8-9). The board is drawn as an instrument
readout rather than a game board, because nothing on it is ground truth: every
cell prints the probability the agent actually holds, so the inference can be
read - and checked - by eye instead of inferred from a colour wash.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from . import theme
from .view_model import (
    banner,
    belief_stats,
    board_cells,
    scent_radius,
    signal_lines,
    telemetry_lines,
)

CELL, GUTTER, POLL_MS = 58, 26, 400
SPARK_W, SPARK_H = 232, 34


class LiveView:
    def __init__(self, status_fn: Any, title: str, role: str = "police") -> None:
        import tkinter as tk

        self._tk = tk
        self.status_fn, self.role = status_fn, role
        self.entropy_history: deque[float] = deque(maxlen=64)
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=theme.GROUND)
        self._build(tk)

    def _build(self, tk: Any) -> None:
        rail = tk.Frame(self.root, bg=theme.GROUND)
        rail.pack(fill="x", padx=18, pady=(16, 10))
        self.eyebrow = tk.Label(rail, text=theme.track(self.role), fg=theme.MUTED,
                                bg=theme.GROUND, font=theme.font("sans", theme.LABEL))
        self.eyebrow.pack(side="left")
        self.banner = tk.Label(rail, text="", fg=theme.MUTED, bg=theme.GROUND,
                               font=theme.font("sans", theme.LABEL))
        self.banner.pack(side="right")

        body = tk.Frame(self.root, bg=theme.GROUND)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self.canvas = tk.Canvas(body, width=GUTTER + CELL * 7, height=GUTTER + CELL * 7,
                                bg=theme.GROUND, highlightthickness=0)
        self.canvas.pack(side="left", anchor="n")

        panel = tk.Frame(body, bg=theme.GROUND)
        panel.pack(side="left", fill="both", expand=True, anchor="n", padx=(22, 0))
        self.spark = tk.Canvas(panel, width=SPARK_W, height=SPARK_H, bg=theme.GROUND,
                               highlightthickness=0)
        self._section(tk, panel, "belief")
        self.readout = tk.Label(panel, text="", fg=theme.INK, bg=theme.GROUND,
                                justify="left", anchor="w",
                                font=theme.font("mono", theme.READOUT))
        self.readout.pack(fill="x")
        self.spark.pack(fill="x", pady=(4, 0))
        self._section(tk, panel, "telemetry")
        self.telemetry = tk.Label(panel, text="", fg=theme.INK, bg=theme.GROUND,
                                  justify="left", anchor="nw",
                                  font=theme.font("mono", theme.BODY))
        self.telemetry.pack(fill="x")
        self._section(tk, panel, "signals")
        self.info = tk.Label(panel, text="", fg=theme.MUTED, bg=theme.GROUND,
                             justify="left", anchor="nw", wraplength=SPARK_W,
                             font=theme.font("sans", theme.BODY))
        self.info.pack(fill="x")

    def _section(self, tk: Any, parent: Any, text: str) -> None:
        tk.Label(parent, text=theme.track(text), fg=theme.MUTED, bg=theme.GROUND,
                 anchor="w", font=theme.font("sans", theme.LABEL)).pack(
            fill="x", pady=(14, 2))
        tk.Frame(parent, height=1, bg=theme.RULE).pack(fill="x", pady=(0, 6))

    # -- drawing -------------------------------------------------------------
    def _draw_board(self, status: dict) -> None:
        cells, n = board_cells(status), status["board_size"]
        self.canvas.configure(width=GUTTER + CELL * n, height=GUTTER + CELL * n)
        self.canvas.delete("all")
        tick = theme.font("mono", theme.MICRO)
        for i in range(n):
            mid = GUTTER + i * CELL + CELL / 2
            self.canvas.create_text(mid, GUTTER / 2, text=str(i), fill=theme.MUTED, font=tick)
            self.canvas.create_text(GUTTER / 2, mid, text=str(i), fill=theme.MUTED, font=tick)
        peak_at, _ = belief_stats(status["belief"])
        for r in range(n):
            for c in range(n):
                self._draw_cell(cells[r][c], r, c, peak_at == (r, c))

    def _draw_cell(self, cell: dict, r: int, c: int, is_peak: bool) -> None:
        x, y = GUTTER + c * CELL, GUTTER + r * CELL
        self.canvas.create_rectangle(x, y, x + CELL, y + CELL, fill=cell["fill"],
                                     outline=cell["outline"], width=cell["width"])
        cx, cy = x + CELL / 2, y + CELL / 2
        if cell["scent"]:  # trace: radius carries intensity, never the fill
            rad = scent_radius(cell["scent"]) * CELL
            self.canvas.create_oval(cx - rad, cy - rad, cx + rad, cy + rad,
                                    outline=theme.TRACE, width=1)
        if cell["text"]:
            self.canvas.create_text(cx, cy, text=cell["text"], fill=theme.PANEL,
                                    font=theme.font("sans", theme.READOUT, bold=True))
        elif not cell["barrier"] and cell["belief"] >= 0.005:
            # The signature: read the posterior, do not infer it from a wash.
            self.canvas.create_text(
                cx, cy, text=f"{cell['belief']:.2f}".lstrip("0"),
                fill=theme.on_field(cell["belief"], self._peak),
                font=theme.font("mono", theme.MICRO))
        if is_peak and not cell["barrier"]:
            # contrast against the cell it marks: the peak cell is the
            # darkest on the ramp, so an ink reticle would vanish into it
            self._reticle(x, y, theme.on_field(cell["belief"], self._peak))

    def _reticle(self, x: float, y: float, colour: str) -> None:
        """Crosshair on the argmax - an instrument marks a reading, it does not
        highlight it."""
        arm, pad = 9, 3
        for dx, dy in ((0, 0), (CELL, 0), (0, CELL), (CELL, CELL)):
            sx, sy = x + dx, y + dy
            hx = -arm if dx else arm
            vy = -arm if dy else arm
            ox, oy = (-pad if dx else pad), (-pad if dy else pad)
            self.canvas.create_line(sx + ox, sy + oy, sx + hx, sy + oy,
                                    fill=colour, width=2)
            self.canvas.create_line(sx + ox, sy + oy, sx + ox, sy + vy,
                                    fill=colour, width=2)

    def _draw_spark(self) -> None:
        """Entropy over time: the agent's uncertainty collapsing as it learns."""
        self.spark.delete("all")
        values = list(self.entropy_history)
        self.spark.create_line(0, SPARK_H - 1, SPARK_W, SPARK_H - 1, fill=theme.RULE)
        if len(values) < 2:
            return
        top = max(values) or 1.0
        step = SPARK_W / max(len(values) - 1, 1)
        points = [(i * step, SPARK_H - 2 - (v / top) * (SPARK_H - 6))
                  for i, v in enumerate(values)]
        self.spark.create_line([p for xy in points for p in xy],
                               fill=theme.FIELD_HI, width=2)

    # -- loop ----------------------------------------------------------------
    def _tick(self) -> None:
        try:
            status = self.status_fn()
        except Exception:  # noqa: BLE001 - runtime may be finishing
            self.root.after(POLL_MS, self._tick)
            return
        text, color = banner(status)
        self.banner.configure(text=theme.track(text), fg=color)
        self.eyebrow.configure(
            text=theme.track(f"{status['role']} / sub-game {status['sub_game']}"))
        self._peak = max(max(row) for row in status["belief"]) or 1.0
        self._draw_board(status)
        peak_at, entropy = belief_stats(status["belief"])
        self.entropy_history.append(entropy)
        self._draw_spark()
        self.readout.configure(
            text=f"peak   {peak_at}  p={self._peak:.3f}\nentropy {entropy:5.2f} bits")
        self.telemetry.configure(text="\n".join(telemetry_lines(status)))
        self.info.configure(text="\n".join(signal_lines(status)[-6:]))
        self.root.after(POLL_MS, self._tick)

    def run(self) -> None:
        self._peak = 1.0
        self.root.after(100, self._tick)
        self.root.mainloop()
