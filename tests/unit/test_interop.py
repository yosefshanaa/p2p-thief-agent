"""Interop with reference-derived peers: dialect detection + message translation.

The reference implementation (rmisegal/Game-P2P-Cop-Chase) exposes a different
tool surface and a different wire message; these tests pin the translation to
the shapes taken from its own source, so a warm-up never has to discover them.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from p2p_pursuit.infra import dialect
from p2p_pursuit.infra import interop_codec as codec
from p2p_pursuit.infra.transport import LinkError
from p2p_pursuit.sdk import PursuitSDK

# The reference TurnMessage dataclass field set, verbatim from its protocol.py.
# Its from_dict() does cls(**data), so an extra key raises TypeError: the
# outbound message must carry exactly these fields, no more.
REFERENCE_TURN_FIELDS = frozenset({
    "step", "sender", "hint", "smell_grid", "commit", "timestamp",
    "barrier_placed", "capture_claim", "claim_response", "win_claim",
})


# -- dialect detection -------------------------------------------------------
@pytest.mark.parametrize(("tools", "expected"), [
    (["handshake", "receive_commit", "receive_reveal", "receive_event",
      "audit_exchange", "health_check"], dialect.NATIVE),
    (["negotiate", "receive_turn", "submit_audit", "receive_control"],
     dialect.REFERENCE),
    (["negotiate", "receive_turn", "submit_audit"], dialect.REFERENCE),
    (["ping", "play"], dialect.UNKNOWN),
    ([], dialect.UNKNOWN),
])
def test_classify_tool_surface(tools, expected):
    assert dialect.classify(tools) == expected


def test_classify_ignores_extra_tools():
    assert dialect.classify(["negotiate", "receive_turn", "submit_audit",
                             "some_extension"]) == dialect.REFERENCE


def test_every_dialect_has_a_human_description():
    for name in (dialect.NATIVE, dialect.REFERENCE, dialect.UNKNOWN):
        assert dialect.describe(name)


# -- scent field: our dense matrix <-> their sparse {"r,c": v} ---------------
def test_scent_to_sparse_grid_drops_zero_cells():
    matrix = [[0.0, 0.9], [0.0, 0.0]]
    assert codec.scent_to_grid(matrix) == {"0,1": 0.9}


def test_scent_round_trips_through_the_sparse_form():
    matrix = [[0.0, 0.81, 0.0], [0.45, 0.0, 0.0], [0.0, 0.0, 0.9]]
    assert codec.grid_to_scent(codec.scent_to_grid(matrix), 3) == matrix


def test_grid_to_scent_ignores_out_of_range_cells():
    assert codec.grid_to_scent({"9,9": 1.0, "0,0": 0.5}, 2) == [[0.5, 0.0], [0.0, 0.0]]


# -- outbound: our commit+reveal -> their single TurnMessage -----------------
def _reveal(**over):
    base = {"kind": "step", "role": "police", "sub_game": 1, "step": 4,
            "barrier": None, "hint": "near the park", "scent": [[0.0, 0.9], [0.0, 0.0]],
            "hash": "a" * 64}
    return {**base, **over}


def test_turn_message_carries_exactly_the_reference_fields():
    msg = codec.to_turn_message(_reveal(), commit_hash="b" * 64)
    assert set(msg) == REFERENCE_TURN_FIELDS


def test_turn_message_maps_our_fields_onto_theirs():
    msg = codec.to_turn_message(_reveal(barrier=[1, 1]), commit_hash="b" * 64)
    assert msg["step"] == 4
    assert msg["sender"] == "police"
    assert msg["hint"] == "near the park"
    assert msg["commit"] == "b" * 64
    assert msg["smell_grid"] == {"0,1": 0.9}
    assert msg["barrier_placed"] == [1, 1]
    assert msg["timestamp"].endswith("+00:00")


def test_capture_claim_travels_as_a_bare_cell():
    msg = codec.to_turn_message(_reveal(claim={"cell": [2, 3], "at_step": 4}),
                                commit_hash="b" * 64)
    assert msg["capture_claim"] == [2, 3]


def test_claim_answer_and_win_claim_ride_the_next_message():
    msg = codec.to_turn_message(_reveal(), commit_hash="b" * 64,
                                claim_response={"claim": [2, 3], "caught": False},
                                win_claim={"type": "survival"})
    assert msg["claim_response"] == {"claim": [2, 3], "caught": False}
    assert msg["win_claim"] == {"type": "survival"}


def test_commit_hash_defaults_to_the_reveal_hash():
    assert codec.to_turn_message(_reveal())["commit"] == "a" * 64


# -- inbound: their TurnMessage -> our commit + reveal ------------------------
def _turn(**over):
    base = {"step": 2, "sender": "thief", "hint": "by the river",
            "smell_grid": {"1,1": 0.9}, "commit": "c" * 64,
            "timestamp": "2026-07-29T00:00:00+00:00", "barrier_placed": None,
            "capture_claim": None, "claim_response": None, "win_claim": None}
    return {**base, **over}


def test_inbound_turn_splits_into_a_commit_and_a_reveal():
    out = codec.from_turn_message(_turn(), sub_game=3, grid_size=2)
    assert out["commit"] == {"kind": "commit", "role": "thief", "sub_game": 3,
                             "step": 2, "hash": "c" * 64}
    assert out["reveal"]["kind"] == "step"
    assert out["reveal"]["hash"] == "c" * 64
    assert out["reveal"]["hint"] == "by the river"
    assert out["reveal"]["scent"] == [[0.0, 0.0], [0.0, 0.9]]


def test_inbound_barrier_and_claim_are_translated():
    out = codec.from_turn_message(
        _turn(barrier_placed=[0, 1], capture_claim=[1, 0]), sub_game=1, grid_size=2)
    assert out["reveal"]["barrier"] == [0, 1]
    assert out["reveal"]["claim"] == {"cell": [1, 0], "at_step": 2}


def test_inbound_side_channels_are_surfaced_separately():
    out = codec.from_turn_message(
        _turn(claim_response={"claim": [1, 1], "caught": True},
              win_claim={"type": "survival"}), sub_game=1, grid_size=2)
    assert out["claim_response"] == {"claim": [1, 1], "caught": True}
    assert out["win_claim"] == {"type": "survival"}


def test_reveal_has_no_claim_key_when_none_was_made():
    out = codec.from_turn_message(_turn(), sub_game=1, grid_size=2)
    assert "claim" not in out["reveal"]


def test_translation_round_trips_our_own_reveal():
    """Our reveal -> their message -> our reveal must preserve every field we act on."""
    original = _reveal(barrier=[1, 1], claim={"cell": [0, 0], "at_step": 4})
    back = codec.from_turn_message(
        codec.to_turn_message(original, commit_hash=original["hash"]),
        sub_game=1, grid_size=2)["reveal"]
    for key in ("kind", "role", "step", "hint", "scent", "barrier", "hash", "claim"):
        assert back[key] == original[key], key


# -- the commit formula: THIS is where the two implementations diverge --------
def test_reference_commit_matches_the_reference_formula():
    """Their digest is sha256(canonical(payload)|nonce) - nonce OUTSIDE the JSON."""
    payload, nonce = {"step": 1, "move": "N"}, "deadbeef"
    expected = hashlib.sha256(
        f'{json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))}'
        f"|{nonce}".encode()).hexdigest()
    assert codec.reference_commit(payload, nonce) == expected


def test_reference_commit_differs_from_our_native_seal():
    """Guards the finding that drove the interop docs: the formulas are NOT the same,
    so a cross-dialect audit cannot verify anything until one side adapts."""
    from p2p_pursuit.domain.crypto import digest

    payload, nonce = {"step": 1, "move": "N"}, "deadbeef"
    assert codec.reference_commit(payload, nonce) != digest({**payload, "nonce": nonce})


def test_reference_verify_accepts_a_matching_record():
    payload, nonce = {"step": 7, "move": "STAY"}, "0123456789abcdef"
    record = {"payload": payload, "nonce": nonce,
              "commit": codec.reference_commit(payload, nonce)}
    assert codec.reference_verify(record) is True


def test_reference_verify_catches_a_tampered_payload():
    payload, nonce = {"step": 7, "move": "STAY"}, "0123456789abcdef"
    record = {"payload": payload, "nonce": nonce,
              "commit": codec.reference_commit(payload, nonce)}
    record["payload"] = {"step": 7, "move": "N"}  # rewritten after the fact
    assert codec.reference_verify(record) is False


class _FakeLink:
    def __init__(self, tools, health=None, fail=False):
        self._tools, self._health, self._fail = tools, health or {}, fail

    def list_tools(self, timeout=None):
        if self._fail:
            raise LinkError("connection refused")
        return list(self._tools)

    def health(self, timeout=None):
        return self._health


def _probe(monkeypatch, link):
    sdk = PursuitSDK()
    monkeypatch.setattr(sdk, "make_link", lambda url: link)
    return sdk.smoke("http://opponent/mcp")


def test_probe_reports_a_reference_peer_as_reachable(monkeypatch):
    """A reference peer has no health_check; it must not read as dead."""
    out = _probe(monkeypatch, _FakeLink(
        ["negotiate", "receive_turn", "submit_audit", "receive_control"]))
    assert out["reachable"] is True
    assert out["dialect"] == dialect.REFERENCE
    assert out["health"] == {}
    assert "interop bridge" in out["guidance"]


def test_probe_of_our_own_peer_includes_health(monkeypatch):
    out = _probe(monkeypatch, _FakeLink(
        ["handshake", "receive_commit", "receive_reveal", "receive_event",
         "audit_exchange", "health_check"], health={"ok": True, "role": "police"}))
    assert out["dialect"] == dialect.NATIVE
    assert out["health"] == {"ok": True, "role": "police"}
    assert out["error"] is None


def test_probe_of_a_dead_endpoint_reports_the_error(monkeypatch):
    out = _probe(monkeypatch, _FakeLink([], fail=True))
    assert out["reachable"] is False
    assert out["dialect"] == dialect.UNKNOWN
    assert "connection refused" in out["error"]


def test_smoke_command_exit_codes(monkeypatch, capsys):
    from p2p_pursuit import cli

    monkeypatch.setattr(cli.PursuitSDK, "smoke",
                        lambda self, url: {"reachable": True, "dialect": dialect.REFERENCE,
                                           "guidance": "g", "tools": [], "health": {},
                                           "error": None})
    assert cli.main(["smoke", "http://x/mcp"]) == 0
    assert json.loads(capsys.readouterr().out)["dialect"] == dialect.REFERENCE

    monkeypatch.setattr(cli.PursuitSDK, "smoke",
                        lambda self, url: {"reachable": False, "dialect": dialect.UNKNOWN,
                                           "guidance": "g", "tools": [], "health": {},
                                           "error": "boom"})
    assert cli.main(["smoke", "http://x/mcp"]) == 4


def test_reference_audit_reports_each_failed_step():
    good = {"step": 1, "move": "N"}
    bad = {"step": 2, "move": "S"}
    records = [
        {"payload": good, "nonce": "aa", "commit": codec.reference_commit(good, "aa")},
        {"payload": bad, "nonce": "bb", "commit": "0" * 64},
    ]
    report = codec.reference_audit(records)
    assert report["passed"] is False
    assert report["verified_steps"] == 1
    assert report["failed_steps"] == [2]
