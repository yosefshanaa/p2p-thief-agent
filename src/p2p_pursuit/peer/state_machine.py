"""The book's mandatory game-phase state machine (ch. 8.3, rules #4-5).

Only transitions listed in the table are possible; anything else raises
immediately, turning logic bugs into loud development-time errors instead
of silent in-game deadlocks. TECHNICAL_LOSS is terminal.
"""

from __future__ import annotations

WAITING_FOR_OPPONENT = "WAITING_FOR_OPPONENT"
COMPUTING_MOVE = "COMPUTING_MOVE"
COMMITTING = "COMMITTING"
AWAITING_REVEAL = "AWAITING_REVEAL"
VERIFYING = "VERIFYING"
TECHNICAL_LOSS = "TECHNICAL_LOSS"


class IllegalTransitionError(RuntimeError):
    pass


class GamePhaseMachine:
    TRANSITIONS: dict[str, set[str]] = {
        WAITING_FOR_OPPONENT: {COMPUTING_MOVE, TECHNICAL_LOSS},
        COMPUTING_MOVE: {COMMITTING, TECHNICAL_LOSS},
        COMMITTING: {AWAITING_REVEAL, TECHNICAL_LOSS},
        AWAITING_REVEAL: {VERIFYING, TECHNICAL_LOSS},
        VERIFYING: {WAITING_FOR_OPPONENT, TECHNICAL_LOSS},
        TECHNICAL_LOSS: set(),
    }

    def __init__(self) -> None:
        self.state = WAITING_FOR_OPPONENT

    def transition(self, target: str) -> str:
        if target not in self.TRANSITIONS[self.state]:
            raise IllegalTransitionError(f"Illegal transition: {self.state} -> {target}")
        self.state = target
        return self.state

    def reset(self) -> None:
        self.state = WAITING_FOR_OPPONENT
