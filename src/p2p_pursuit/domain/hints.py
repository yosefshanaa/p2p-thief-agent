"""Free natural-language hints: compass/landmark regions, tolerant parsing.

The verbal channel is mandatory free text (rules #26-27) - never coordinates.
Both generation and parsing share one region vocabulary so our own hints are
parseable, while unknown opponents' text degrades gracefully to "no info".
"""

from __future__ import annotations

import re

from .board import Cell

COMPASS = (
    "northwest", "northeast", "southwest", "southeast",
    "north", "south", "east", "west", "center", "centre", "middle",
)

# Landmark vocabulary per map area; region key -> spoken names (book: [map area]).
LANDMARKS: dict[str, dict[str, list[str]]] = {
    "New York": {
        "north": ["Harlem", "the Bronx line"],
        "south": ["Wall Street", "Battery Park"],
        "east": ["the East River piers"],
        "west": ["the Hudson docks"],
        "center": ["Times Square", "Grand Central"],
        "northwest": ["Riverside Park"],
        "northeast": ["the Harlem River bridge"],
        "southwest": ["the Staten Island ferry"],
        "southeast": ["Brooklyn Bridge"],
    },
    "": {
        "north": ["the north gate"],
        "south": ["the south docks"],
        "east": ["the east bridge"],
        "west": ["the west tower"],
        "center": ["the old market"],
        "northwest": ["the mill ruins"],
        "northeast": ["the granary"],
        "southwest": ["the fish wharf"],
        "southeast": ["the salt store"],
    },
}


def region_cells(name: str, size: int) -> set[Cell]:
    """Cells of a compass region: board thirds, compounds intersect."""
    lo, hi = size / 3.0, 2.0 * size / 3.0
    name = {"centre": "center", "middle": "center"}.get(name, name)

    def rows(part: str) -> set[int]:
        if part == "north":
            return {r for r in range(size) if r < lo}
        if part == "south":
            return {r for r in range(size) if r >= hi}
        return {r for r in range(size) if lo <= r < hi}

    def cols(part: str) -> set[int]:
        if part == "west":
            return {c for c in range(size) if c < lo}
        if part == "east":
            return {c for c in range(size) if c >= hi}
        return {c for c in range(size) if lo <= c < hi}

    v = "north" if "north" in name else "south" if "south" in name else "center"
    h = "west" if "west" in name else "east" if "east" in name else "center"
    if name == "center":
        v = h = "center"
    return {(r, c) for r in rows(v) for c in cols(h)}


def region_of(cell: Cell, size: int) -> str:
    """Compass name of the region containing ``cell`` (used to phrase hints)."""
    lo, hi = size / 3.0, 2.0 * size / 3.0
    v = "north" if cell[0] < lo else "south" if cell[0] >= hi else ""
    h = "west" if cell[1] < lo else "east" if cell[1] >= hi else ""
    return (v + h) if (v or h) else "center"


def landmark_for(region: str, map_area: str, index: int = 0) -> str:
    table = LANDMARKS.get(map_area, LANDMARKS[""])
    names = table.get(region) or LANDMARKS[""].get(region) or [region]
    return names[index % len(names)]


def parse_hint(text: str, size: int, map_area: str) -> set[Cell] | None:
    """Best-effort extraction of a board region from free text; None = no info."""
    low = text.lower()
    for region in COMPASS:
        if re.search(rf"\b{region}\b", low):
            return region_cells(region, size)
    for table in (LANDMARKS.get(map_area, {}), LANDMARKS[""]):
        for region, names in table.items():
            for name in names:
                if name.lower() in low:
                    return region_cells(region, size)
    return None


def clip_words(text: str, max_words: int) -> str:
    """Enforce the negotiated word cap on every outgoing hint."""
    words = text.split()
    return " ".join(words[:max_words])
