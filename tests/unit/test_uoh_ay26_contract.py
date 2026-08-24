"""uoh-ay26's Step-0 convention, which they refuse the offer without.

Their pairing document makes two demands the PDF leaves implementation-specific,
and both are gates rather than preferences:

  1. the negotiation identity carries a **top-level** `git_commit_hash` of
     exactly 40 lowercase hex characters;
  2. the revealed audit **begins** with a sealed step-0 record whose payload
     carries at least `{"step": 0, "type": "system_spec"}`, attached to the
     records list - "building it without attaching it to AuditPayload.records
     causes verification failure at step 0".

We already sealed the step-0 record for amireman, who reads the same value under
the name `github_commit`. Only the identity field was missing, and a missing
field there is a refusal at negotiation, not a degraded report.
"""

from __future__ import annotations

import re
from pathlib import Path

from p2p_pursuit.domain import protocol
from p2p_pursuit.domain.crypto import REFERENCE, seal
from p2p_pursuit.infra.interop_codec import interop_identity, reference_records
from p2p_pursuit.shared.config import load_role

HEX40 = re.compile(r"^[0-9a-f]{40}$")


def identity():
    _, peer = load_role(Path(__file__).resolve().parents[2] / "config" / "police")
    return interop_identity(peer, mcp_url="https://x/mcp",
                            spec={"machine": "x86_64", "gpu": "none"},
                            counted_games_played=5)


def test_the_identity_carries_a_top_level_git_commit_hash():
    value = identity().get("git_commit_hash")
    assert value is not None, "uoh-ay26 refuse an offer without this field"
    assert HEX40.match(value), f"must be 40 lowercase hex, got {value!r}"


def test_both_spellings_are_sent_and_agree():
    """amireman read `github_commit`; uoh-ay26 read `git_commit_hash`.

    Sending one spelling only trades a refusal with one team for a wrong
    per-sub-game commit filed by the other, so both go out - and they must
    never disagree, which is the thing worth asserting.
    """
    block = identity()
    assert block["git_commit_hash"] == block["github_commit"]


def test_the_commit_is_a_real_hash_not_the_unknown_sentinel():
    """`sysinfo.git_commit` falls back to the literal 'unknown' outside a repo,
    and that string would satisfy neither their regex nor an auditor."""
    assert identity()["git_commit_hash"] != "unknown"


def test_the_step_zero_record_is_sealed_cached_and_shaped_as_they_require():
    """Minimum payload is step 0 + type system_spec; ours adds the commit.

    Cached rather than minted per call: a retried `submit_audit` that re-sealed
    it would reveal one claim under two commitments, which is equivocation.
    """
    import inspect

    from p2p_pursuit.infra.interop_bridge import ReferenceBridge

    # Read the method, not a file: the bridge is assembled from mixins, so a
    # filename is a guess about where the code lives and `getsource` is not.
    source = inspect.getsource(ReferenceBridge._system_spec_record)
    assert '"type": "system_spec"' in source
    assert '"step": 0' in source
    assert "self._system_specs[sub_game] = sealed" in source, "must be cached"


def test_every_auxiliary_record_has_the_generic_step_their_audit_requires():
    """F002 failed only on our thief rounds because capture answers exposed
    ``at_step`` but their structural verifier indexes every payload by ``step``.

    The alias must be present *before sealing*. Adding it while building the
    audit package would change the payload after its live commitment and turn a
    schema mismatch into an actual hash mismatch.
    """
    records = [
        protocol.capture_answer_record(
            role="thief", sub_game=2, at_step=7,
            claim_cell=(5, 5), answer=False),
        protocol.captured_event_record(
            role="thief", sub_game=2, at_step=8, cause="barrier"),
        protocol.survival_claim_record(
            role="thief", sub_game=2, steps=35),
    ]

    for payload in records:
        expected = payload.get("at_step", payload.get("steps"))
        assert payload["step"] == expected
        sealed, commit = seal(payload, REFERENCE)
        revealed = reference_records([sealed], [commit])[0]
        assert revealed["payload"]["step"] == expected
        assert {"payload", "nonce", "commit"} <= revealed.keys()
