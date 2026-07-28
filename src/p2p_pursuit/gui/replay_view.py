"""Replay viewer: step through a sealed log with live hash re-verification.

Green "Verified OK" stamp per verified state; a single mismatch raises the
red TAMPERED banner and the match is void (rule #20). Post-game evidence -
here (and only here) both trajectories are legitimately visible.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.audit import VERIFIED_OK
from .replay_data import frames, load_log, verdict_of

CELL = 56


class ReplayView:
    def __init__(self, log_path: Path) -> None:
        import tkinter as tk

        self.log = load_log(log_path)
        self.frames = frames(self.log)
        self.verdict, _, _ = verdict_of(self.log)
        self.index = 0
        self.root = tk.Tk()
        self.root.title(f"Replay - {log_path.name}")
        ok = self.verdict == VERIFIED_OK
        self.banner = tk.Label(self.root, text=self.verdict,
                               font=("TkDefaultFont", 16, "bold"), fg="white",
                               bg="#22aa44" if ok else "#cc2222")
        self.banner.pack(fill="x")
        n = self._size()
        self.canvas = tk.Canvas(self.root, width=CELL * n, height=CELL * n, bg="white")
        self.canvas.pack(padx=4, pady=4)
        bar = tk.Frame(self.root)
        bar.pack(fill="x")
        tk.Button(bar, text="<< prev", command=lambda: self._go(-1)).pack(side="left")
        tk.Button(bar, text="next >>", command=lambda: self._go(+1)).pack(side="left")
        self.playing = False
        self.play_btn = tk.Button(bar, text="play", width=6, command=self._toggle_play)
        self.play_btn.pack(side="left", padx=4)
        self.speed = tk.StringVar(value="1x")
        tk.OptionMenu(bar, self.speed, "0.5x", "1x", "2x", "4x").pack(side="left")
        self.label = tk.Label(bar, text="")
        self.label.pack(side="left", padx=8)
        self._draw()

    def _toggle_play(self) -> None:
        self.playing = not self.playing
        self.play_btn.configure(text="pause" if self.playing else "play")
        if self.playing:
            self._advance()

    def _advance(self) -> None:
        if not self.playing:
            return
        if self.index >= len(self.frames) - 1:
            self._toggle_play()  # reached the end - flip back to "play"
            return
        self._go(+1)
        delay = int(600 / float(self.speed.get().rstrip("x")))
        self.root.after(delay, self._advance)

    def _size(self) -> int:
        cells = [p for f in self.frames for p in f["positions"].values()]
        return max([7] + [max(c) + 1 for c in cells]) if cells else 7

    def _go(self, delta: int) -> None:
        self.index = max(0, min(len(self.frames) - 1, self.index + delta))
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("all")
        n = self._size()
        if not self.frames:
            return
        frame = self.frames[self.index]
        for r in range(n):
            for c in range(n):
                x, y = c * CELL, r * CELL
                fill = "#222222" if (r, c) in frame["barriers"] else "#ffffff"
                self.canvas.create_rectangle(x, y, x + CELL, y + CELL,
                                             fill=fill, outline="#cccccc")
        colors = {"police": "#2266dd", "thief": "#dd6622"}
        for role, pos in frame["positions"].items():
            x, y = pos[1] * CELL, pos[0] * CELL
            self.canvas.create_oval(x + 8, y + 8, x + CELL - 8, y + CELL - 8,
                                    fill=colors.get(role, "#999999"))
            self.canvas.create_text(x + CELL / 2, y + CELL / 2, text=role[0].upper(),
                                    fill="white", font=("TkDefaultFont", 14, "bold"))
        stamp = "Verified OK" if frame["verified"] else "TAMPERED"
        self.label.configure(
            text=f"{self.index + 1}/{len(self.frames)}  {frame['role']} step "
                 f"{frame['step']}  [{stamp}]  hint: {frame['hint'][:40]}")

    def run(self) -> None:
        self.root.mainloop()
