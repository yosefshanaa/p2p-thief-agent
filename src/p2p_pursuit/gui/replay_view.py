"""Replay viewer: step a sealed log while re-hashing every record.

The verdict is the subject here, so it is set as a stamp rather than a status
bar, and the ledger rail beneath the board gives one tick per sealed record -
each tick coloured by its OWN re-verification. A reader can see the whole chain
was checked, not just the frame on screen (rule #20). This is the one surface
where both trajectories are legitimately visible: the match is over.
"""

from __future__ import annotations

from pathlib import Path

from . import theme
from .replay_data import frames, load_log, verdict_of
from .replay_layout import CELL, RAIL_H, ReplayLayout


class ReplayView(ReplayLayout):
    def __init__(self, log_path: Path) -> None:
        import tkinter as tk

        self._tk = tk
        self.log = load_log(log_path)
        self.frames = frames(self.log)
        self.verdict, _, _ = verdict_of(self.log)
        self.index, self.playing = 0, False
        self.root = tk.Tk()
        self.root.title(f"replay - {log_path.name}")
        self.root.configure(bg=theme.GROUND)
        self._build(tk)
        self._bind()
        self._draw()

    def _bind(self) -> None:
        for seq, fn in (("<Left>", lambda _e: self._go(-1)),
                        ("<Right>", lambda _e: self._go(+1)),
                        ("<Home>", lambda _e: self._jump(0)),
                        ("<End>", lambda _e: self._jump(len(self.frames) - 1)),
                        ("<space>", lambda _e: self._toggle_play())):
            self.root.bind(seq, fn)

    # -- playback ------------------------------------------------------------
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
        self.root.after(int(600 / float(self.speed.get().rstrip("x"))), self._advance)

    def _size(self) -> int:
        cells = [p for f in self.frames for p in f["positions"].values()]
        return max([7] + [max(c) + 1 for c in cells]) if cells else 7

    def _on_rail(self, event) -> None:
        if self.frames:
            width = max(self.rail.winfo_width(), 1)
            self._jump(int(event.x / width * len(self.frames)))

    def _go(self, delta: int) -> None:
        self._jump(self.index + delta)

    def _jump(self, index: int) -> None:
        self.index = max(0, min(len(self.frames) - 1, index))
        self._draw()

    # -- drawing -------------------------------------------------------------
    def _draw(self) -> None:
        self.canvas.delete("all")
        if not self.frames:
            return
        frame, n = self.frames[self.index], self._size()
        for r in range(n):
            for c in range(n):
                x, y = c * CELL, r * CELL
                barred = (r, c) in frame["barriers"]
                self.canvas.create_rectangle(
                    x, y, x + CELL, y + CELL,
                    fill=theme.INK if barred else theme.PANEL, outline=theme.RULE)
        for role, pos in frame["positions"].items():
            self._agent(role, pos)
        self._draw_rail()
        verified = frame["verified"]
        self.fields["record"].configure(
            text=f"step {frame['step']}   {frame['role']}\n"
                 f"{'re-hash matches' if verified else 'RE-HASH MISMATCH'}",
            fg=theme.INK if verified else theme.ALARM)
        self.fields["hint"].configure(text=frame["hint"] or "-", fg=theme.MUTED)
        digest = self.log.get("my_hashes", []) + self.log.get("opponent_hashes", [])
        commit = digest[self.index] if self.index < len(digest) else ""
        self.fields["commitment"].configure(
            text="\n".join(commit[i:i + 16] for i in range(0, 32, 16)) or "-",
            fg=theme.MUTED)
        self.counter.configure(text=f"{self.index + 1} / {len(self.frames)}")

    def _agent(self, role: str, pos) -> None:
        x, y = pos[1] * CELL, pos[0] * CELL
        self.canvas.create_oval(x + 9, y + 9, x + CELL - 9, y + CELL - 9,
                                fill=theme.ROLE.get(role, theme.MUTED), outline="")
        self.canvas.create_text(x + CELL / 2, y + CELL / 2, text=role[0].upper(),
                                fill=theme.PANEL,
                                font=theme.font("sans", theme.BODY, bold=True))

    def _draw_rail(self) -> None:
        """One tick per sealed record, coloured by its own re-verification."""
        self.rail.delete("all")
        width = max(self.rail.winfo_width(), self.rail.winfo_reqwidth(), 1)
        step = width / max(len(self.frames), 1)
        for i, frame in enumerate(self.frames):
            self.rail.create_rectangle(
                i * step, 4, i * step + max(step - 1, 1), RAIL_H - 4,
                fill=theme.ASSURE if frame["verified"] else theme.ALARM, outline="")
        cursor = self.index * step
        self.rail.create_rectangle(cursor - 1, 0, cursor + max(step, 2) + 1, RAIL_H,
                                   outline=theme.INK, width=2)

    def run(self) -> None:
        self.root.mainloop()
