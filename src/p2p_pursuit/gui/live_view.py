"""Live Tkinter GUI: belief heatmap + turn banner, local truth only (book ch. 7.3).

Polls the peer service snapshot; input is display-only, so the turn lockout
is inherent. tkinter imports lazily - headless runs never touch it.
"""

from __future__ import annotations

from typing import Any

from .view_model import banner, board_cells, info_lines

CELL = 56
POLL_MS = 400


class LiveView:
    def __init__(self, status_fn: Any, title: str) -> None:
        import tkinter as tk

        self._tk = tk
        self.status_fn = status_fn
        self.root = tk.Tk()
        self.root.title(title)
        self.banner = tk.Label(self.root, text="...", font=("TkDefaultFont", 14, "bold"),
                               fg="white", bg="#888888", width=40)
        self.banner.pack(fill="x")
        self.canvas = tk.Canvas(self.root, width=CELL * 7, height=CELL * 7, bg="white")
        self.canvas.pack(side="left", padx=4, pady=4)
        self.info = tk.Text(self.root, width=44, height=24, state="disabled")
        self.info.pack(side="right", fill="y")

    def _tick(self) -> None:
        try:
            status = self.status_fn()
        except Exception:  # noqa: BLE001 - runtime may be finishing
            self.root.after(POLL_MS, self._tick)
            return
        text, color = banner(status)
        self.banner.configure(text=text, bg=color)
        cells = board_cells(status)
        n = status["board_size"]
        self.canvas.configure(width=CELL * n, height=CELL * n)
        self.canvas.delete("all")
        for r in range(n):
            for c in range(n):
                cell = cells[r][c]
                x, y = c * CELL, r * CELL
                self.canvas.create_rectangle(x, y, x + CELL, y + CELL,
                                             fill=cell["fill"],
                                             outline=cell["outline"],
                                             width=cell["width"])
                if cell["text"]:
                    self.canvas.create_text(x + CELL / 2, y + CELL / 2, text=cell["text"],
                                            fill="white", font=("TkDefaultFont", 16, "bold"))
                if cell["ring"]:
                    self.canvas.create_oval(x + 6, y + 6, x + CELL - 6, y + CELL - 6,
                                            outline="#aa1111", width=2)
        lines = info_lines(status)
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", "\n".join(lines))
        self.info.configure(state="disabled")
        self.root.after(POLL_MS, self._tick)

    def run(self) -> None:
        self.root.after(100, self._tick)
        self.root.mainloop()
