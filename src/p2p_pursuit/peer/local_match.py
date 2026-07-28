"""In-process series driver: two TurnEngines, full protocol, no sockets.

The tactics lab (PRD-3) and the integration harness: exercises the exact
commit/reveal/claim/audit paths the network runner uses, deterministically
seeded, fast enough for tournaments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.rules import POLICE, THIEF
from ..domain.scoring import TECHNICAL_LOSS
from ..shared.config import PeerConfig, SharedConfig
from . import audit_bridge
from .turn_engine import TurnEngine


@dataclass
class SubGameOutcome:
    index: int
    ending: str
    winner: str
    cause: str
    police_score: int
    thief_score: int
    thief_steps: int
    audit_of_thief: dict[str, Any]
    audit_of_police: dict[str, Any]


@dataclass
class SeriesResult:
    sub_games: list[SubGameOutcome] = field(default_factory=list)
    police_total: int = 0
    thief_total: int = 0
    tokens_used: int = 0

    @property
    def series_winner(self) -> str:
        if self.police_total > self.thief_total:
            return POLICE
        return THIEF if self.thief_total > self.police_total else "tie"


def play_sub_game(police: TurnEngine, thief: TurnEngine) -> None:
    """Drive one sub-game to its end, strictly alternating per the protocol."""
    engines = {POLICE: police, THIEF: thief}
    guard = 0
    while police.end is None or thief.end is None:
        guard += 1
        if guard > 500:
            raise RuntimeError("sub-game did not terminate (protocol bug)")
        mover = engines[police.next_mover]
        observer = engines[mover.other]
        if mover.end is not None:
            break
        package = mover.build_own_step()
        if "commit" in package:
            observer.on_commit(package["commit"])
            mover.sent_commit()
            response = observer.on_reveal(package["reveal"])
            mover.sent_reveal()
            mover.process_reveal_response(response)
        if package.get("event"):
            observer.on_event(package["event"])


def run_series(shared: SharedConfig, police_cfg: PeerConfig, thief_cfg: PeerConfig, *,
               num_games: int | None = None, seed: int | None = None,
               engines_out: list | None = None, on_sub_game=None) -> SeriesResult:
    result = SeriesResult()
    games = num_games or shared.num_games
    police = TurnEngine(POLICE, shared, police_cfg, seed=None if seed is None else seed * 2)
    thief = TurnEngine(THIEF, shared, thief_cfg, seed=None if seed is None else seed * 2 + 1)
    if engines_out is not None:
        engines_out.extend([police, thief])
    for n in range(1, games + 1):
        police.start_sub_game(n)
        thief.start_sub_game(n)
        play_sub_game(police, thief)
        verdict_t, viol_t = audit_bridge.run_audit(police, audit_bridge.audit_package(thief))
        verdict_p, viol_p = audit_bridge.run_audit(thief, audit_bridge.audit_package(police))
        ending, winner, cause = police.end.ending, police.end.winner, police.end.cause
        if verdict_t != "Verified OK":
            ending, winner, cause = TECHNICAL_LOSS, POLICE, "thief log TAMPERED"
        if verdict_p != "Verified OK":
            ending, winner, cause = TECHNICAL_LOSS, THIEF, "police log TAMPERED"
        p_score, t_score = police.score_table.score(ending)
        result.sub_games.append(SubGameOutcome(
            index=n, ending=ending, winner=winner, cause=cause,
            police_score=p_score, thief_score=t_score, thief_steps=thief.my_steps,
            audit_of_thief={"verdict": verdict_t, "violations": viol_t},
            audit_of_police={"verdict": verdict_p, "violations": viol_p}))
        result.police_total += p_score
        result.thief_total += t_score
        if on_sub_game is not None:
            on_sub_game(police, thief, result.sub_games[-1])
    result.tokens_used = police.tokens_used + thief.tokens_used
    return result
