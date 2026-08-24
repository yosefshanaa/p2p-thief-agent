"""Widget construction for the replay viewer, as a single-concern mixin.

Split out of :mod:`.replay_view` so both files stay inside the guidelines'
150-line limit (§3.2), using the mixin strategy the guidelines name for a class
carrying more than one responsibility (ch. 4.2). This mixin owns layout only -
header, board canvas, inspector panel, ledger rail, transport bar - and
overrides nothing the view defines. Drawing and navigation stay in
:class:`~.replay_view.ReplayView`.
"""

from __future__ import annotations

from ..domain.audit import VERIFIED_OK
from . import theme

CELL, PAD, RAIL_H = 58, 20, 18


class ReplayLayout:
    """Builds the widget tree.

    Reads ``self.verdict``, ``self.log``, ``self.frames`` and ``self.root``;
    sets ``self.canvas``, ``self.rail``, ``self.fields``, ``self.play_btn``,
    ``self.speed`` and ``self.counter`` on the view that mixes it in.
    """


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
