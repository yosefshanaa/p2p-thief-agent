"""The per-sub-game audit ledger, frozen at the boundary - as a mixin.

Split out of :mod:`.engine_state` (§3.2, mixin strategy ch. 4.2). One concern:
what we committed, what the opponent committed, and the snapshot handed to the
mutual audit. The freeze is per sub-game on purpose - filing a reveal by
arrival time is what makes a late package land against the wrong window.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from ..domain import protocol


def _now() -> str:
    """The single definition. `engine_state` imports it from here rather than
    keeping a second one - two of these drifted apart once and moved every
    audit package's `ended_at` from `+00:00` to `Z`."""
    return datetime.now(UTC).isoformat(timespec="seconds")

class EngineAudit:
    # -- the audit ledger ---------------------------------------------------
    def freeze_audit(self) -> dict[str, Any] | None:
        """Seal this sub-game's reveal into the ledger, once and for good.

        Called the moment the sub-game ends and again at the boundary, so the
        (payload, nonce) pairs we later reveal are literally the objects that
        produced the commitments we sent - copied, so nothing that arrives
        afterwards can edit them, and written once, so a late event cannot
        overwrite a package we have already handed out.
        """
        n = getattr(self, "sub_game", 0)
        if n <= 0 or not hasattr(self, "my_records") or n in self.audit_ledger:
            return self.audit_ledger.get(n)
        # Anything played counts, from either side: a sub-game where only the
        # opponent moved still has their commitments and their clock to preserve,
        # and gating on our own records alone loses both.
        if not (self.my_records or self.opp_hashes or self.end is not None):
            return None
        snapshot = {
            "sub_game": n,
            "role": self.role,
            "records": copy.deepcopy(self.my_records),
            "hashes": list(self.my_hashes),
            # What the opponent committed to *in play* here, so their reveal can
            # still be audited against the right sub-game when it arrives late.
            "opp_hashes": list(self.opp_hashes),
            # Frozen with the records, and for the same reason: the log is
            # written after the audit exchange, so reading the clock then would
            # time the paperwork rather than the sub-game.
            "started_at": self.started_at,
            "ended_at": _now(),
            "opp_turn_times": list(self.opp_turn_times),
        }
        self.audit_ledger[n] = snapshot
        return snapshot

    def opponent_hashes_for(self, n: int) -> list[str]:
        """Commitments the opponent sent us during sub-game ``n``."""
        if n == self.sub_game:
            return list(self.opp_hashes)
        snapshot = self.audit_ledger.get(n)
        return list(snapshot["opp_hashes"]) if snapshot else []

    def audit_snapshot(self, n: int | None = None) -> dict[str, Any]:
        """The frozen reveal for sub-game ``n`` (this one by default).

        Falls back to freezing now for a sub-game still in flight, so a caller
        can never be handed a *different* sub-game's records by accident.
        """
        n = self.sub_game if n is None else n
        if n == self.sub_game:
            self.freeze_audit()
        return self.audit_ledger.get(
            n, {"sub_game": n, "role": self.role, "records": [], "hashes": [],
                "opp_hashes": [], "started_at": self.started_at, "ended_at": None,
                "opp_turn_times": []})

    def _record(self, sealed: dict, commit_hash: str) -> dict:
        self.my_records.append(sealed)
        self.my_hashes.append(commit_hash)
        return protocol.public_view(sealed, commit_hash)

    def _note_opp(self, commit_hash: str, public: dict | None) -> None:
        self.opp_hashes.append(commit_hash)
        self.opp_public.append(public)
