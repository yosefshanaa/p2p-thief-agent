"""Replay viewer: step a sealed log while re-hashing every record.

The verdict is the subject here, so it is set as a stamp rather than a status
bar, and the ledger rail beneath the board gives one tick per sealed record -
each tick coloured by its OWN re-verification. A reader can see the whole chain
was checked, not just the frame on screen (rule #20). This is the one surface
where both trajectories are legitimately visible: the match is over.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.audit import VERIFIED_OK
from . import theme
from .replay_data import frames, load_log, verdict_of

CELL, PAD, RAIL_H = 58, 20, 18


class ReplayView:
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

    def _build(self, tk) -> None:
        ok = self.verdict == VERIFIED_OK
        head = tk.Frame(self.root, bg=theme.GROUND)
        head.pack(fill="x", padx=PAD, pady=(16, 0))
        tk.Label(head, text=self.verdict, fg=theme.ASSURE if ok else theme.ALARM,
                 bg=theme.GROUND, font=theme.font("roman", theme.VERDICT, bold=True)
                 ).pack(side="left")
        tk.Label(head, text=theme.track("re-hashed per record"), fg=theme.MUTED,
                 bg=theme.GROUND, font=theme.font("sans", theme.LABEL)).pack(
            side="left", padx=(14, 0))
        tk.Frame(self.root, height=1, bg=theme.RULE).pack(fill="x", padx=PAD, pady=(10, 12))

        body = tk.Frame(self.root, bg=theme.GROUND)
        body.pack(fill="both", expand=True, padx=PAD)
        n = self._size()
        self.canvas = tk.Canvas(body, width=CELL * n, height=CELL * n,
                                bg=theme.GROUND, highlightthickness=0)
        self.canvas.pack(side="left")
        self._inspector(tk, body)

        self.rail = tk.Canvas(self.root, height=RAIL_H, bg=theme.GROUND,
                              highlightthickness=0)
        self.rail.pack(fill="x", padx=PAD, pady=(14, 4))
        self.rail.bind("<Button-1>", self._on_rail)
        self.rail.bind("<Configure>", lambda _e: self._draw_rail())
        self._controls(tk)

    def _inspector(self, tk, body) -> None:
        """The record under the cursor, in the terms the audit uses."""
        panel = tk.Frame(body, bg=theme.GROUND)
        panel.pack(side="left", fill="both", expand=True, padx=(26, 0))
        self.fields: dict[str, object] = {}
        for name in ("record", "hint", "commitment"):
            tk.Label(panel, text=theme.track(name), fg=theme.MUTED, bg=theme.GROUND,
                     anchor="w", font=theme.font("sans", theme.LABEL)).pack(
                fill="x", pady=(0 if name == "record" else 16, 2))
            tk.Frame(panel, height=1, bg=theme.RULE).pack(fill="x", pady=(0, 6))
            face = "mono" if name == "commitment" else "sans"
            size = theme.BODY if name == "commitment" else theme.READOUT
            label = tk.Label(panel, text="", fg=theme.INK, bg=theme.GROUND, anchor="nw",
                             justify="left", wraplength=300,
                             font=theme.font(face, size))
            label.pack(fill="x")
            self.fields[name] = label
        tk.Frame(panel, height=1, bg=theme.RULE).pack(fill="x", pady=(20, 6))
        meta = (f"sub-game {self.log.get('sub_game', '?')}   "
                f"view {self.log.get('perspective', '?')}\n"
                f"config {str(self.log.get('config_sha256', ''))[:12]}")
        tk.Label(panel, text=meta, fg=theme.MUTED, bg=theme.GROUND, anchor="nw",
                 justify="left", font=theme.font("mono", theme.MICRO)).pack(fill="x")

    def _controls(self, tk) -> None:
        bar = tk.Frame(self.root, bg=theme.GROUND)
        bar.pack(fill="x", padx=PAD, pady=(10, 16))
        for text, cmd in (("first", lambda: self._jump(0)),
                          ("prev", lambda: self._go(-1)),
                          ("next", lambda: self._go(+1)),
                          ("last", lambda: self._jump(len(self.frames) - 1))):
            tk.Button(bar, text=text, command=cmd, relief="flat", bd=0,
                      fg=theme.INK, bg=theme.PANEL, activebackground=theme.RULE,
                      font=theme.font("sans", theme.BODY), padx=10, pady=3).pack(
                side="left", padx=(0, 6))
        self.play_btn = tk.Button(bar, text="play", command=self._toggle_play,
                                  relief="flat", bd=0, fg=theme.PANEL, bg=theme.FIELD_HI,
                                  activebackground=theme.INK, width=6,
                                  font=theme.font("sans", theme.BODY), padx=10, pady=3)
        self.play_btn.pack(side="left", padx=(6, 6))
        self.speed = tk.StringVar(value="1x")
        menu = tk.OptionMenu(bar, self.speed, "0.5x", "1x", "2x", "4x")
        menu.configure(relief="flat", bd=0, bg=theme.PANEL, fg=theme.INK,
                       highlightthickness=0, font=theme.font("sans", theme.BODY))
        menu.pack(side="left")
        self.counter = tk.Label(bar, text="", fg=theme.MUTED, bg=theme.GROUND,
                                font=theme.font("mono", theme.BODY))
        self.counter.pack(side="right")

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
