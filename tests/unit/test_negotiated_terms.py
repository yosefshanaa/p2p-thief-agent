"""Per-opponent negotiated terms, and the counters that cross this dialect's wire.

A reference-derived peer compares agreed terms by exact dict equality, so terms
are settled per opponent - but the committed constitution must never be edited
to settle one, or that edit silently rides into the next match.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2p_pursuit.infra.interop_codec import handshake_from_agreement, interop_identity
from p2p_pursuit.shared.config import load_shared

CONSTITUTION = Path("config/police/game.json")


def test_negotiated_terms_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = load_shared(CONSTITUTION)
    monkeypatch.setenv("P2P_HINT_MAX_WORDS", "30")
    monkeypatch.setenv("P2P_MIN_CENTER_INTENSITY", "0.001")
    monkeypatch.setenv("P2P_AXIS_ORIGIN_CORNER", "top_left")
    monkeypatch.setenv("P2P_MAP_AREA", "7x7")
    adopted = load_shared(CONSTITUTION)

    assert adopted.hint_max_words == 30
    assert adopted.pheromones["pheromone_min_center_intensity"] == 0.001
    assert adopted.raw["board_and_agents"]["axis_origin_corner"] == "top_left"
    assert adopted.map_area == "7x7"
    # A different constitution must hash differently...
    assert adopted.sha256 != baseline.sha256
    # ...and the file on disk must be untouched by any of it.
    assert json.loads(CONSTITUTION.read_text(encoding="utf-8"))["world"]["hint_max_words"] == 15


def test_malformed_override_raises_rather_than_defaulting(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Silently falling back would play a term neither side agreed to."""
    monkeypatch.setenv("P2P_HINT_MAX_WORDS", "thirty")
    with pytest.raises(ValueError, match="P2P_HINT_MAX_WORDS"):
        load_shared(CONSTITUTION)


class _Peer:
    group_id = "ahk-yosi"
    group_name = "ahk-yosi"
    members = ("213314859", "325811255")
    repos = {"cop": "https://example/cop", "thief": "https://example/thief"}
    llm_model = "gpt-5.6-luna"


def test_identity_declares_the_counted_count_in_their_spelling() -> None:
    identity = interop_identity(_Peer(), mcp_url="http://x/mcp", spec={},
                                counted_games_played=2)
    assert identity["counted_games_played"] == 2
    assert identity["prior_counted_games"] == 2  # our own readers keep working


def test_their_counted_count_is_read_from_their_field_name() -> None:
    """They send `counted_games_played`; reading only our name files a 0 we invented."""
    agreement = {"terms": {}, "nonce": "", "signature": "",
                 "identity": {"group_id": "uoh-sqak", "counted_games_played": 3}}
    payload = handshake_from_agreement(agreement, mine={"role": "police"}, terms={})
    assert payload["prior_counted_games"] == 3
