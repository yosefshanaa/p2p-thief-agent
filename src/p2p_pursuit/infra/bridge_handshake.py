"""Agreeing terms with a reference-dialect peer - as a mixin.

Split out of :mod:`.interop_bridge` (§3.2, mixin strategy ch. 4.2). One
concern: everything said before the first move - the negotiate answer, the
constitution we offer and the one we accept, the HMAC-signed envelope, the
Step-0 declaration and the hardware record inside it.
"""

from __future__ import annotations

import logging
import queue
import time
from typing import Any

from . import interop_codec as codec
from .transport import LinkError

log = logging.getLogger(__name__)

class BridgeHandshake:
    # -- inbound: their pushes into our server -------------------------------
    def on_negotiate(self, message: dict) -> dict:
        self.agreements.put(message)
        return {"ok": True}

    def step0(self, payload: dict, timeout: float | None = None) -> dict:
        """Forward Step-0 to the real client.

        The bridge *replaces* the link once the reference dialect is on
        (`runtime.attach`), so anything the runtime calls on `rt.link` and the
        bridge does not define is silently unreachable. `send_step0` guards with
        `getattr(rt.link, "step0", None)` and returns None when it is missing -
        no log line, no error, and no declaration merged on their side, which
        their counted backend then refuses at the end of window 1. That is the
        2026-08-24 friendly, and it cost a played window.
        """
        return self.link.step0(payload, timeout=timeout)

    def handshake(self, payload: dict, timeout: float | None = None) -> dict:
        """Push our signed agreement, then take theirs for THIS window off the inbox.

        Their slug rides the **negotiate answer**, top level - `{"ok": true,
        "group_id": "..."}` - which is the shape we asked MaRs-777 for and then
        discarded, reading only the agreement they push separately. That one
        carries no group_id, so we logged "opponent sent no group_id", kept
        locally-minted ids and voided every digest between us while their fix
        was deployed and correct the whole time.
        """
        answer = self.link.negotiate(self._signed(), timeout=timeout)
        theirs = self._agreement_for(self.service.engine.sub_game, timeout or 60)
        hs = codec.handshake_from_agreement(theirs, mine=payload, terms=self.terms)
        gid = (answer or {}).get("group_id") if isinstance(answer, dict) else None
        if gid and not hs.get("group_id"):
            hs["group_id"] = gid
        return hs

    def _agreement_for(self, n: int, timeout: float) -> dict:
        """Their agreement for window ``n``, discarding ones already settled.

        The inbox is a FIFO and this used to take whatever was oldest, which is
        wrong against any peer that retries - and retrying into a busy peer is
        normal, specified behaviour, not a fault. A peer running two processes
        against our one hands us the same problem from the other direction: its
        police handshakes window N+1 at our single door while we are still mid
        window N, and every one of its retries leaves another agreement behind.

        Taking the oldest then consumes one stale agreement per boundary, for
        the rest of the series: after a burst of k retries we open every later
        window on an agreement k-1 windows out of date, and the queue never
        drains. najamjad named this exact scenario before we dialled, on the
        strength of a 2026-08-02 session where 58 negotiates arrived into one
        game state - which was ours.

        Only *older* agreements are dropped, never newer ones. A window we have
        already settled cannot be re-opened by a late message, so discarding it
        is free; but an agreement for a window ahead of us means their index has
        drifted past ours, and that is recovered by adopting their side rather
        than by ignoring them (`_adopt_complementary_role`). So it is put back.
        """
        deadline = time.monotonic() + timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                theirs = self.agreements.get(timeout=remaining)
                mine = theirs.get("sub_game_number")
                if mine is None or mine >= n:
                    return theirs
                log.info("discarding an agreement for sub-game %s while opening %s "
                         "- that window is settled; their retry, not their fault", mine, n)
        except queue.Empty as exc:
            raise LinkError("opponent never sent its agreement") from exc

    def _signed(self) -> dict:
        from ..domain.crypto import new_nonce, reference_commit

        nonce = new_nonce()
        # `sub_game_number` rides outside `terms`, so it cannot disturb the
        # signature - but without it a peer that has advanced past us looks
        # identical to one in step, and the two series drift in silence.
        #
        # `sender` and `group_id` are at the TOP LEVEL and duplicated inside
        # `identity` on purpose. Several peers bind the session on a top-level
        # field and never look inside a nested block: najamjad §9.8 log
        # `session.unauthenticated` and refuse to bind us, which is a refusal
        # that looks exactly like an outage. Nesting the id was not wrong so
        # much as unreadable, and the fix costs two keys. `sender` is our role
        # rather than our slug because it also tells the receiver which of our
        # two doors is speaking - their contract accepts either spelling.
        # `role`, `game_uid` and `scent_model_sha256` are lifted from the native
        # handshake we already build, because a cross-check nobody can perform is
        # not a cross-check. vibecode audited our Step-0 after F001 and found we
        # send none of them: we had written "we declare it at Step-0" about the
        # scent hash and on the wire we did not, and the labelled-uid agreement we
        # spent two mails settling never actually exercised against their value.
        # Their gate refuses on disagreement, not omission, so all three were
        # silently unverifiable in both directions. Supersets are accepted here,
        # so adding them costs nothing and makes the wire match the contract.
        #
        # `sender` stays: it is our role under the name their contract reads for
        # door selection, and `role` is the same value under the reference name.
        # The uid is the one value here that is NOT safe to send unconditionally.
        # `_adopt_shared_ids` runs AFTER the opening handshake (runtime.py:172,
        # sent at :161), so the very first greeting still holds the locally
        # minted `uuid4().hex[:12]` - a value no opponent can derive. Sending
        # that where a peer cross-checks the uid is strictly worse than sending
        # nothing: omission refuses nothing under this gate, disagreement is what
        # aborts a series. The derived value is a full dashed UUID and the minted
        # one never is, so shape alone separates them without new state.
        # `getattr` rather than attribute access: this greeting is built by
        # bridges wired to a bare service in tests and in the loopback
        # harness, and a Step-0 field is a courtesy - never a reason for the
        # handshake itself to raise.
        mine = getattr(self.service, "my_handshake", None) or {}
        signed = {"terms": self.terms, "nonce": nonce,
                  "signature": reference_commit(self.terms, nonce),
                  "sub_game_number": self.service.engine.sub_game,
                  "sender": self.service.engine.role,
                  "role": mine.get("role", self.service.engine.role),
                  "scent_model_sha256": mine.get("scent_model_sha256", ""),
                  "group_id": self.identity.get("group_id", ""),
                  "identity": self.identity}
        game_uid = str(mine.get("game_uid", ""))
        if "-" in game_uid:
            signed["game_uid"] = game_uid
        return signed

    def _system_spec_record(self, sub_game: int) -> tuple[dict[str, Any], str]:
        """The step-0 record naming the code that played this sub-game.

        A reference peer reads `github_commit` out of our *revealed records* and
        files it per sub-game; there is nowhere else in this dialect for it to
        come from, so omitting the record does not leave their report blank -
        it leaves it saying `unknown` about us. Sealed like any other record so
        the claim is bound rather than asserted.

        Sealed **once per sub-game and cached**: this used to mint a fresh nonce
        on every call, so a retried `submit_audit` revealed the same claim under
        two different commitments. Nothing about an audit may be generated at
        audit time.
        """
        cached = self._system_specs.get(sub_game)
        if cached is not None:
            return cached
        from ..domain.crypto import commit_digest, new_nonce
        from ..shared import sysinfo

        engine = self.service.engine
        record = {"kind": "system_spec", "type": "system_spec", "step": 0,
                  "role": engine.audit_snapshot(sub_game)["role"],
                  "sub_game": sub_game, "sub_game_number": sub_game,
                  "github_commit": sysinfo.git_commit(), "nonce": new_nonce()}
        sealed = (record, commit_digest(record, engine.commit_dialect))
        self._system_specs[sub_game] = sealed
        return sealed
