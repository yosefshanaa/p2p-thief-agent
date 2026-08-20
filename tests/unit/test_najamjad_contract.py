"""najamjad's contract, and the three defects it exposed in ours.

Their terms document (2026-08-20) is the first opponent contract we checked by
re-deriving rather than by reading, and both of their published vectors
reproduce through our own code with no configuration change at all. What it
found instead were three things on *our* side, each of which would have failed
silently:

* our ``negotiate`` carried the group id only inside a nested ``identity``
  block, and they bind the session on a top-level field (their §9.8);
* our identity block published the address we *bind* - ``0.0.0.0:<port>``, the
  same value for both roles - so their handshake recovery, which re-sends its
  agreement "to the address your identity declares", dialled a loopback address
  twice and read us as offline;
* our series loop advanced past a window that abandoned, while theirs re-offers
  it under the same number. Two peers advancing at different rates desynchronise
  permanently, and they report it ending three series on consecutive evenings.

The first two are always-on corrections. The third is per-opponent, because a
peer that does *not* re-offer would read our replay of N as a stale duplicate.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from p2p_pursuit.domain.crypto import digest, reference_commit
from p2p_pursuit.domain.game_ids import reference_game_id, reference_game_uid
from p2p_pursuit.domain.scoring import CAPTURE, TECHNICAL_LOSS
from p2p_pursuit.infra.interop_codec import interop_identity, interop_terms
from p2p_pursuit.shared import sysinfo
from p2p_pursuit.shared.config import apply_env_overrides, load_role, load_shared

#: Published in their §1 and §5. Ours must reproduce both from our own code.
THEIR_TERMS_SHA = "a284082dfb1572236f1b614d29295a99625539c7d33a096f7f8921bafbc3d08d"
THEIR_COMMIT_VECTOR = "4047830b8108320cbf48c1c1e1f09c6c0d47da51c225ce2cf40c7857cefc3030"
#: The kit's registered subtractive document, which both teams adopted verbatim.
SHARED_SCENT_LOCK = "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4"


@pytest.fixture
def police() -> tuple:
    return load_role(Path("config/police"))


def test_their_commit_reveal_vector_reproduces_through_our_crypto() -> None:
    """Their §5 offline vector, hashed by the function that seals our own steps."""
    payload = {"hint": "", "intent": "probe east", "move": "MOVE:E",
               "position": [3, 4], "role": "thief", "state": "ok",
               "step": 1, "sub_game": 1}
    assert reference_commit(payload, "a" * 32) == THEIR_COMMIT_VECTOR


def test_our_shipped_constitution_already_signs_their_fourteen_terms(police) -> None:
    """No config change: the object we put on the wire IS their fourteen keys.

    Checked as a set as well as a digest, because a coincidence of hashes would
    be extraordinary but an extra key we happened to send is exactly the sort of
    thing that refuses a handshake for a reason neither side can see.
    """
    shared, _ = police
    terms = interop_terms(shared, num_games=None)
    assert set(terms) == {
        "axis_origin_corner", "axis_start_index", "barriers_max", "board_size",
        "cop_start", "decay_per_step", "emit_intensity", "hint_max_words",
        "max_steps", "min_center_intensity", "num_games", "setting",
        "smell_grid_size", "thief_start"}
    assert digest(terms) == THEIR_TERMS_SHA


def test_both_role_configs_sign_the_same_terms() -> None:
    """Two processes, one contract. A split here signs half a series differently."""
    ours = [interop_terms(load_shared(Path(f"config/{role}/game.json")), num_games=None)
            for role in ("police", "thief")]
    assert ours[0] == ours[1]
    assert digest(ours[0]) == THEIR_TERMS_SHA


def test_the_derived_ids_both_sides_must_land_on() -> None:
    """Their §6, which neither peer sends: we each derive it and it must agree.

    `game_id` is the first signed key of the mutual result signature, so a
    difference here is a digest mismatch at the end of a clean series - which is
    why the najamjad contract carries no `game_id_label`.
    """
    terms = interop_terms(load_shared(Path("config/police/game.json")), num_games=None)
    assert reference_game_id("ahk-yosi", "najamjad") == "ahk-yosi-vs-najamjad"
    assert reference_game_uid(terms, "ahk-yosi", "najamjad") == \
        "c581764c-4c29-50a6-f800-a5d416ef9536"


def test_a2_is_the_only_scent_lock_that_can_bind_between_us() -> None:
    """Both teams adopted the kit's subtractive document; neither adopted the
    other's book one. `check_compatibility` refuses on a scent-hash difference,
    so this is what makes A2 the only startable option rather than the nicer one.
    """
    from p2p_pursuit.domain.negotiation import scent_model_sha256

    assert scent_model_sha256("subtractive_chebyshev_v1") == SHARED_SCENT_LOCK
    # Ours; theirs is 934c220d..., the kit's. Same physics, different documents.
    assert scent_model_sha256("book_v1") != \
        "934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9"


def test_our_negotiate_names_us_at_the_top_level(monkeypatch) -> None:
    """Their §9.8: a group id only inside `identity` logs session.unauthenticated.

    The nested copy stays - a native reader and amireman both use it - so this
    is two added keys, not a move.
    """
    from p2p_pursuit.infra.interop_bridge import ReferenceBridge

    bridge = ReferenceBridge.__new__(ReferenceBridge)
    bridge.terms = {"board_size": 7}
    bridge.identity = {"group_id": "ahk-yosi", "group_name": "ahk-yosi"}
    bridge.service = type("S", (), {"engine": type("E", (), {"sub_game": 3,
                                                             "role": "police"})()})()
    signed = bridge._signed()
    assert signed["group_id"] == "ahk-yosi"
    assert signed["sender"] == "police"
    assert signed["sub_game_number"] == 3
    assert signed["identity"]["group_id"] == "ahk-yosi", "the nested copy is still owed"
    assert signed["signature"] == reference_commit(bridge.terms, signed["nonce"])


def test_the_identity_block_publishes_a_reachable_door_per_role(police) -> None:
    """The bug this replaces published `0.0.0.0` twice - unreachable, and one
    door claimed for two roles while we run two processes on two ports."""
    _, peer = police
    peer = replace(peer, public_doors={"police": "https://cop.example/mcp",
                                       "thief": "https://thief.example/mcp"})
    ident = interop_identity(peer, mcp_url="http://0.0.0.0:8802/mcp",
                             spec=sysinfo.collect(), public_doors=peer.public_doors)
    assert ident["mcp_servers"] == {"cop": "https://cop.example/mcp",
                                    "thief": "https://thief.example/mcp"}


def test_the_bind_address_remains_the_fallback(police) -> None:
    """Honest for a local match, and harmless to a peer that never reads it."""
    _, peer = police
    ident = interop_identity(peer, mcp_url="http://0.0.0.0:8802/mcp",
                             spec=sysinfo.collect(), public_doors=None)
    assert ident["mcp_servers"] == {"cop": "http://0.0.0.0:8802/mcp",
                                    "thief": "http://0.0.0.0:8802/mcp"}


def test_a_reoffered_window_does_not_reveal_the_abandoned_attempt() -> None:
    """The subtle half of the re-offer, and the one that fails silently.

    `freeze_audit` is write-once per index and `start_sub_game` freezes on the
    way in, so the attempt that abandoned seals itself under N first. Without
    the eviction the replay's records are dropped and we reveal an EMPTY package
    for a sub-game we really played - a failed audit with no visible cause.
    """
    from p2p_pursuit.peer.engine_state import EngineState

    shared, peer = load_role(Path("config/police"))
    engine = EngineState("police", shared, peer)
    engine.begin_sub_game(1)
    engine._record({"step": 1, "nonce": "ab" * 16}, "deadbeef")
    engine.declare_technical("thief", "no re-handshake")
    assert engine.audit_ledger[1]["hashes"] == ["deadbeef"], "the corpse is sealed"

    engine.reoffer_sub_game(1)
    assert 1 not in engine.audit_ledger, "the abandoned attempt must be evicted"
    assert engine.end is None and engine.my_records == []
    engine._record({"step": 1, "nonce": "cd" * 16}, "cafe")
    assert engine.audit_snapshot(1)["hashes"] == ["cafe"], "the replay must be revealed"


def test_only_a_technical_ending_re_offers() -> None:
    """A capture or a survival is a window that was played, however badly."""
    from p2p_pursuit.peer.engine_state import EngineState

    shared, peer = load_role(Path("config/police"))
    engine = EngineState("police", shared, peer)
    engine.begin_sub_game(1)
    engine._finish(CAPTURE, "police", "caught at [3,3]")
    assert engine.end is not None and engine.end.ending != TECHNICAL_LOSS


def test_re_offering_is_off_by_default_and_on_for_najamjad(monkeypatch, police) -> None:
    """Per-opponent, like every other interop divergence: a peer that does not
    re-offer would read our replay of N as a stale duplicate."""
    _, peer = police
    assert peer.window_reoffers == 0

    for key, value in _env_of("config/opponents/najamjad.env").items():
        monkeypatch.setenv(key, value)
    tuned = apply_env_overrides(peer)
    assert tuned.window_reoffers == 2
    assert tuned.handshake_budget_sec == tuned.rehandshake_budget_sec == 1000
    assert tuned.scent_model == "subtractive_chebyshev_v1"
    assert tuned.claim_enclosure is False
    assert tuned.series_consensus is False
    assert tuned.trash_talk_provider == "template"


def test_the_friendly_contract_never_mails_the_lecturer() -> None:
    """Their §7.4 and ours agree: friendlies go to the two teams only."""
    env = _env_of("config/opponents/najamjad.env")
    assert env["P2P_EMAIL_RECIPIENT"] == "apexmediamind@gmail.com"
    assert "rmisegal" not in env["P2P_EMAIL_RECIPIENT"]


def test_the_contract_leaves_the_game_id_label_unset() -> None:
    """Their §6 has no label slot, and `game_id` is the first signed key of the
    mutual signature - a label on one side alone guarantees a mismatch."""
    assert "P2P_GAME_ID" not in _env_of("config/opponents/najamjad.env")


def test_their_doors_are_addressed_per_role() -> None:
    """Their cop and thief are two processes on two hostnames; ours must dial
    the one holding the other role and flip at every boundary."""
    from p2p_pursuit.shared.config import opponent_url_for

    env = _env_of("config/opponents/najamjad.env")
    doors = {"police": env["P2P_OPPONENT_COP_URL"], "thief": env["P2P_OPPONENT_THIEF_URL"]}
    assert doors["police"] != doors["thief"]
    assert opponent_url_for("", "thief", doors) == "https://thief.4laboratory.com/mcp"
    assert opponent_url_for("", "police", doors) == "https://cop.4laboratory.com/mcp"


def _env_of(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def test_the_env_file_parses_and_sets_nothing_unexpected() -> None:
    """Every key must be one the loader actually reads, or it is a silent no-op
    in a file whose whole purpose is to be believed."""
    from p2p_pursuit.shared.config import (
        BOOL_VARS,
        DIALECT_VAR,
        EMAIL_MODE_VAR,
        EMAIL_RECIPIENT_VAR,
        INT_VARS,
        OPPONENT_DOOR_VARS,
        SCENT_MODEL_VAR,
        TRASH_TALK_VAR,
    )
    from p2p_pursuit.strategy.params import DOCTRINE_PATH_VAR

    known = (set(BOOL_VARS) | set(INT_VARS) | set(OPPONENT_DOOR_VARS.values())
             | {DIALECT_VAR, SCENT_MODEL_VAR, EMAIL_MODE_VAR, EMAIL_RECIPIENT_VAR,
                TRASH_TALK_VAR, DOCTRINE_PATH_VAR})
    unknown = set(_env_of("config/opponents/najamjad.env")) - known
    assert not unknown, f"these keys are read by nothing: {sorted(unknown)}"


def test_an_unparseable_patience_knob_is_loud(monkeypatch, police) -> None:
    """A typo that silently reverted a budget to its default would surface only
    as an unexplained technical loss mid-series."""
    _, peer = police
    monkeypatch.setenv("P2P_HANDSHAKE_BUDGET", "1000s")
    with pytest.raises(ValueError, match="P2P_HANDSHAKE_BUDGET"):
        apply_env_overrides(peer)


def test_the_archive_is_untouched() -> None:
    """Nothing in this work may edit a filed match."""
    before = json.dumps(sorted(p.name for p in Path("matches").iterdir()))
    assert "najamjad" not in before


def test_a_retrying_peer_does_not_leave_us_one_window_behind_forever() -> None:
    """najamjad's scenario, named by them before we dialled and reproduced here.

    They run two processes against our one, so their police handshakes window
    N+1 at our single door while we are still mid window N - and every retry
    leaves another agreement in our inbox. Taking the FIFO's oldest then spends
    one stale agreement per boundary for the rest of the series.

    The 2026-08-02 session that voided between these two teams put 58 negotiates
    into one game state. This is that failure, in a unit test.
    """
    import queue as _queue

    from p2p_pursuit.infra.interop_bridge import ReferenceBridge

    bridge = ReferenceBridge.__new__(ReferenceBridge)
    bridge.agreements = _queue.Queue()
    # Three retries for window 1 while we played it, then the real one for 2.
    for _ in range(3):
        bridge.agreements.put({"sub_game_number": 1, "tag": "stale"})
    bridge.agreements.put({"sub_game_number": 2, "tag": "live"})

    assert bridge._agreement_for(2, timeout=1.0)["tag"] == "live"
    assert bridge.agreements.empty(), "the stale retries must be drained, not deferred"


def test_an_agreement_for_a_later_window_is_never_discarded() -> None:
    """Their index drifting PAST ours is recovered by adopting their side, not
    by ignoring them - so only windows we have already settled may be dropped."""
    import queue as _queue

    from p2p_pursuit.infra.interop_bridge import ReferenceBridge

    bridge = ReferenceBridge.__new__(ReferenceBridge)
    bridge.agreements = _queue.Queue()
    bridge.agreements.put({"sub_game_number": 5, "tag": "they are ahead"})
    assert bridge._agreement_for(3, timeout=1.0)["tag"] == "they are ahead"


def test_an_agreement_with_no_index_is_still_accepted() -> None:
    """`sub_game_number` is our addition and theirs; a peer that sends neither
    must not be refused for it."""
    import queue as _queue

    from p2p_pursuit.infra.interop_bridge import ReferenceBridge

    bridge = ReferenceBridge.__new__(ReferenceBridge)
    bridge.agreements = _queue.Queue()
    bridge.agreements.put({"tag": "no index"})
    assert bridge._agreement_for(4, timeout=1.0)["tag"] == "no index"


def test_a_door_with_only_stale_agreements_times_out_rather_than_hanging() -> None:
    """Bounded: draining must not become an unbounded wait."""
    import queue as _queue

    from p2p_pursuit.infra.interop_bridge import ReferenceBridge
    from p2p_pursuit.infra.transport import LinkError

    bridge = ReferenceBridge.__new__(ReferenceBridge)
    bridge.agreements = _queue.Queue()
    bridge.agreements.put({"sub_game_number": 1})
    with pytest.raises(LinkError, match="never sent its agreement"):
        bridge._agreement_for(3, timeout=0.2)


def test_the_counted_contract_mails_the_lecturer_and_the_friendly_never_does() -> None:
    """The one line that differs between the two files, and the only one that
    cannot be got wrong twice: a friendly filed to the lecturer reads as THE
    counted encounter, and the book allows exactly one per pair."""
    friendly = _env_of("config/opponents/najamjad.env")
    counted = _env_of("config/opponents/najamjad-counted.env")
    lecturer = "rmisegal+uoh26finalgame@gmail.com"

    assert friendly["P2P_EMAIL_RECIPIENT"] == "apexmediamind@gmail.com"
    assert counted["P2P_EMAIL_RECIPIENT"] == lecturer
    assert counted["P2P_EMAIL_MODE"] == friendly["P2P_EMAIL_MODE"] == "send"


def test_the_two_contracts_agree_on_everything_except_the_recipient() -> None:
    """A counted series must be played on the terms the warm-up proved. Any
    other drift between these two files is a setting that was never rehearsed.
    """
    friendly = _env_of("config/opponents/najamjad.env")
    counted = _env_of("config/opponents/najamjad-counted.env")
    differing = {k for k in set(friendly) | set(counted)
                 if friendly.get(k) != counted.get(k)}
    assert differing == {"P2P_EMAIL_RECIPIENT"}, (
        f"unrehearsed drift between friendly and counted: {sorted(differing)}")
