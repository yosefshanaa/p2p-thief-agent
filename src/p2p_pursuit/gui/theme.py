"""Design tokens for both viewers.

The interface is dressed as a **laboratory instrument**, not a game board,
because that is what it actually is: neither agent can see its opponent, so
every surface here reports an *inference* over a diffusing chemical trace
(book ch. 4) rather than a position. Two consequences drive every choice below.

Type is Latin Modern - Knuth's Computer Modern, the typeface of the papers this
project is written against. Telemetry sets in its typewriter cut, section
labels in its sans, verdicts in its roman.

Colour encodes quantity and nothing else. One sequential ramp carries the
posterior; the pheromone trace is a *different* quantity, so it is encoded by
radius in ochre instead of a second fill that would compete with the first.
"""

from __future__ import annotations

INK = "#191f26"        # text
GROUND = "#e4e9ec"     # bench
PANEL = "#edf1f3"      # raised panel / zero-probability cell
RULE = "#aebbc3"       # hairline
MUTED = "#5f6e77"      # secondary text
FIELD_HI = "#0f4c5c"   # posterior at the peak
TRACE = "#b26b24"      # pheromone trace
ALARM = "#a61b3c"      # tampered, loss, technical
ASSURE = "#2f6b4f"     # verified, win
ROLE = {"police": "#123f52", "thief": "#5b2a50"}

_STACKS = {
    "mono": ("latin modern typewriter", "nimbus mono l", "courier"),
    "sans": ("latin modern sans", "texgyreheros", "nimbus sans l", "helvetica"),
    "roman": ("latin modern roman", "texgyretermes", "times"),
}
_resolved: dict[str, str] = {}

MICRO, LABEL, BODY, READOUT, VERDICT = 9, 10, 12, 15, 20


def family(role: str) -> str:
    """First installed family for a role, resolved once per process."""
    if role not in _resolved:
        import tkinter.font as tkfont

        available = {name.lower() for name in tkfont.families()}
        picks = [f for f in _STACKS[role] if f.lower() in available]
        _resolved[role] = picks[0] if picks else "TkDefaultFont"
    return _resolved[role]


def font(role: str, size: int, bold: bool = False) -> tuple:
    return (family(role), size, "bold") if bold else (family(role), size)


def track(text: str, gap: str = " ") -> str:
    """Letter-spaced label. Tk has no tracking, so the spacing is literal -
    used only on short uppercase eyebrows, the way instrument panels label."""
    return gap.join(text.upper())


def _mix(lo: str, hi: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    pairs = [(int(lo[i:i + 2], 16), int(hi[i:i + 2], 16)) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in pairs)


def field_fill(value: float, peak: float) -> str:
    """Sequential ramp for one posterior cell: bench -> deep petrol at the peak."""
    if peak <= 0:
        return PANEL
    return _mix(PANEL, FIELD_HI, value / peak)


def on_field(value: float, peak: float) -> str:
    """Text colour that stays legible as the ramp darkens under it."""
    ratio = 0.0 if peak <= 0 else max(0.0, min(1.0, value / peak))
    return PANEL if ratio > 0.55 else MUTED
