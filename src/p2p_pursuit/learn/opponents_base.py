"""Shared primitives for the sparring archetypes: the unreachable-distance
sentinel and two geometry helpers.

Split out of :mod:`.opponents` (§3.2 - split, never compress) because the
archetype families below all need them and none of them owns them."""

from __future__ import annotations

from ..domain.board import Cell

FAR = 99


def _manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(here: Cell, there: Cell) -> str:
    if there[0] < here[0]:
        return "N"
    if there[0] > here[0]:
        return "S"
    return "E" if there[1] > here[1] else "W"
