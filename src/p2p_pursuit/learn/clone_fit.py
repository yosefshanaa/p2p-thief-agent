"""Fit a playable policy to an opponent's observed moves, then play it.

A linear score over eight features, chosen by CEM to reproduce as many of the
opponent's real decisions as possible. Linear and small on purpose: a few
hundred decisions is what a match yields, and anything with more capacity than
that would memorise the trajectory rather than generalise the policy.

One honest limitation, stated because it bounds what the clone is worth: the
features use *our* position, not their estimate of it. They were reacting to a
belief we cannot reconstruct. So the clone captures a team's revealed style -
does it flee straight, hold the middle, hug walls, spend barriers - and not
their inference machinery.
"""

from __future__ import annotations

import random

from ..domain.board import Board, Cell, target_of
from ..domain.brains_base import BrainBase, BrainView
from ..domain.rules import Decision
from ..strategy.pathing import bfs_distances
from .cem import search_unit
from .clone_data import Sample

FEATURES = ("pursuer_dist", "mobility", "mobility2", "edge", "centre",
            "stay", "straight", "reverse")
REVERSE = {"N": "S", "S": "N", "E": "W", "W": "E"}
WEIGHT_RANGE = 4.0  # unit cube maps to [-4, +4] per weight
FAR = 99


def features(board: Board, pos: Cell, move: str, pursuer: Cell,
             prev_move: str | None, dist: dict[Cell, int] | None = None) -> dict[str, float]:
    """Describe one candidate move the way a simple agent would weigh it."""
    dist = bfs_distances(board, pursuer) if dist is None else dist
    cell = target_of(pos, move)
    size = board.size
    room = board.open_neighbors(cell)
    mid = (size - 1) / 2
    return {
        "pursuer_dist": min(dist.get(cell, FAR), size * 2) / size,
        "mobility": len(room) / 4.0,
        "mobility2": sum(len(board.open_neighbors(n)) for n in room) / 16.0,
        "edge": ((cell[0] in (0, size - 1)) + (cell[1] in (0, size - 1))) / 2.0,
        "centre": 1.0 - (abs(cell[0] - mid) + abs(cell[1] - mid)) / (2 * mid),
        "stay": 1.0 if move == "STAY" else 0.0,
        "straight": 1.0 if prev_move and move == prev_move else 0.0,
        "reverse": 1.0 if prev_move and move == REVERSE.get(prev_move) else 0.0,
    }


def _best_move(board: Board, pos: Cell, pursuer: Cell, prev_move: str | None,
               weights: dict[str, float], rng: random.Random | None = None) -> str:
    """Argmax of the linear score. ``rng`` breaks ties at play time; fitting
    leaves it out so agreement is a deterministic function of the weights."""
    dist = bfs_distances(board, pursuer)

    def value(move: str) -> float:
        feat = features(board, pos, move, pursuer, prev_move, dist)
        jitter = rng.random() * 1e-6 if rng is not None else 0.0
        return sum(weights.get(k, 0.0) * v for k, v in feat.items()) + jitter

    return max(board.legal_moves(pos), key=value)


def agreement(weights: dict[str, float], samples: list[Sample]) -> float:
    """Fraction of the opponent's real moves this weight vector reproduces."""
    if not samples:
        return 0.0
    hits = 0
    for s in samples:
        board = Board(s.size, set(s.barriers))
        hits += _best_move(board, s.pos, s.pursuer, s.prev_move, weights) == s.move
    return hits / len(samples)


def _weights_of(unit: list[float]) -> dict[str, float]:
    return {name: (value * 2 - 1) * WEIGHT_RANGE
            for name, value in zip(FEATURES, unit, strict=True)}


def fit(samples: list[Sample], *, generations: int = 14, population: int = 40,
        seed: int = 0) -> tuple[dict[str, float], float]:
    """Recover the weights that best explain a set of observed decisions."""
    if not samples:
        return dict.fromkeys(FEATURES, 0.0), 0.0

    def batch(points: list[list[float]]) -> list[float]:
        return [agreement(_weights_of(point), samples) for point in points]

    result = search_unit(len(FEATURES), batch, generations=generations,
                         population=population, sigma=0.30, seed=seed)
    return _weights_of(result.best), result.best_score


def fit_by_role(samples: list[Sample], **kwargs) -> dict[str, dict[str, float]]:
    """One weight vector per role the opponent was observed playing."""
    out = {}
    for role in {s.role for s in samples}:
        weights, _ = fit([s for s in samples if s.role == role], **kwargs)
        out[role] = weights
    return out


class ClonedBrain(BrainBase):
    """Plays fitted weights, estimating the pursuer the way our own brains do."""

    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = dict(weights)
        self._last_move: str | None = None

    def _pursuer(self, view: BrainView) -> Cell:
        top = max(max(row) for row in view.opp_scent)
        if top > 0.0:
            size = view.board.size
            return max(((r, c) for r in range(size) for c in range(size)),
                       key=lambda cell: view.opp_scent[cell[0]][cell[1]])
        return view.belief.argmax()

    def _pick_move(self, view: BrainView) -> Decision:
        if view.step <= 1:
            self._last_move = None
        move = _best_move(view.board, view.own_pos, self._pursuer(view),
                          self._last_move, self.weights, rng=view.rng)
        self._last_move = move
        return Decision(move=move)
