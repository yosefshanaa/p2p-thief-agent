"""Which wire contract does the peer at the other end speak?

The book leaves the tool surface to each pair of teams, so two honest
implementations of the same rules can be mutually unreachable. Classifying the
opponent's advertised MCP tools turns that from a mid-match surprise into a
warm-up fact (RUNBOOK 3b).
"""

from __future__ import annotations

from collections.abc import Iterable

NATIVE = "native"
REFERENCE = "reference"
UNKNOWN = "unknown"

#: Ours - the book's four-phase figure, request/response.
NATIVE_TOOLS = frozenset({"handshake", "receive_commit", "receive_reveal", "audit_exchange"})
#: The lecturer's example repo - one message per turn, pushed into inboxes.
REFERENCE_TOOLS = frozenset({"negotiate", "receive_turn", "submit_audit"})

_DESCRIPTIONS = {
    NATIVE: ("native four-phase surface (handshake / receive_commit -> receive_reveal "
             "-> receive_event / audit_exchange); play directly"),
    REFERENCE: ("reference-derived surface (negotiate / receive_turn / submit_audit / "
                "receive_control): one fire-and-forget message per turn, replies arrive "
                "as pushes to our own server - needs the interop bridge"),
    UNKNOWN: ("unrecognised tool surface - agree the contract with the team by hand "
              "before playing anything counted"),
}


def classify(tool_names: Iterable[str]) -> str:
    """Name the dialect an opponent speaks, from the tools it advertises."""
    names = set(tool_names)
    if names >= NATIVE_TOOLS:
        return NATIVE
    if names >= REFERENCE_TOOLS:
        return REFERENCE
    return UNKNOWN


def describe(name: str) -> str:
    """One-line operator guidance for a classified dialect."""
    return _DESCRIPTIONS.get(name, _DESCRIPTIONS[UNKNOWN])
