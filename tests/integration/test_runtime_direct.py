"""Two full PeerRuntimes joined by DirectLinks: series, audits, artifacts, email."""

import json
import threading
from pathlib import Path

from p2p_pursuit.infra.email_sender import DryRunTransport
from p2p_pursuit.infra.transport import DirectLink
from p2p_pursuit.peer.runtime import PeerRuntime

BASE = Path(__file__).resolve().parent.parent.parent


def _rename_group(rt, group_id: str) -> None:
    """Point a runtime at a different team slug, handshake included."""
    from dataclasses import replace

    rt.peer = replace(rt.peer, group_id=group_id, group_name=group_id)
    rt.service.my_handshake["group_id"] = group_id
    rt.service.my_handshake["group_name"] = group_id


def test_runtime_pair_full_series(tmp_path):
    police = PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path,
                         seed=1, num_games=2)
    thief = PeerRuntime("thief", BASE / "config" / "thief", out_dir=tmp_path,
                        seed=2, num_games=2)
    # Both role configs ship OUR group id, so a self-play pairing would key every
    # group-keyed field on one slug and collapse the two teams into one. Give the
    # far side a distinct id, which is the only case a real league ever presents.
    _rename_group(thief, "uoh-other")
    assert police.connect(DirectLink(thief.service))
    assert thief.connect(DirectLink(police.service))

    results = {}

    def run(rt: PeerRuntime, name: str) -> None:
        results[name] = rt.run_series()

    threads = [threading.Thread(target=run, args=(thief, "thief"), daemon=True),
               threading.Thread(target=run, args=(police, "police"), daemon=True)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=240)
    assert set(results) == {"police", "thief"}

    p, t = results["police"], results["thief"]
    assert p["totals"] == t["totals"], "peers must agree on every score"
    assert p["series_winner"] == t["series_winner"]
    # The reference family's cross-check, and the strongest one we have: two
    # peers that agree byte-for-byte on the projection of the series. It is
    # computed from opposite chairs - each side's own role, own scores, own
    # group id first - so a matching digest means the disagreement space is
    # empty, not merely that both sides ran the same code.
    assert p["mutual_signature"] == t["mutual_signature"]
    assert p["aggregate"] == t["aggregate"], "the signed aggregate must be symmetric"
    for res in (p, t):
        for row in res["sub_games"]:
            assert row["audit"] == "Verified OK"
            assert row["ending"] in {"capture", "survival"}
        assert res["mutual_agreement"] is True and res["result_sha256"]

    # all four Appendix-F artifacts exist on each side
    for rt in (police, thief):
        files = sorted(f.name for f in rt.out_dir.iterdir())
        assert any(f.startswith("declaration_") for f in files)
        assert sum(f.startswith("config_") for f in files) == 2
        assert sum(f.startswith("log_") for f in files) == 2
        assert any(f.startswith("result_") for f in files)
        log = json.loads(next(rt.out_dir.glob("log_*_g01.json")).read_text())
        assert log["audit"]["mine_of_them"]["verdict"] == "Verified OK"

    # gatekeeper-guarded dry-run report from both sides independently (#35).
    # The transport is injected, so nothing leaves the machine whatever the
    # configured mode is; assert the configured mode reaches the transport
    # rather than pinning draft/send, which toggles for league play.
    for rt, res in ((police, p), (thief, t)):
        transport = DryRunTransport()
        receipt = rt.report(res, transport)
        assert receipt["delivered"]
        assert transport.sent[0]["mode"] == rt.peer.email_mode
        assert rt.peer.email_mode in {"draft", "send"}


def test_runtime_refuses_on_constitution_mismatch(tmp_path):
    police = PeerRuntime("police", BASE / "config" / "police", out_dir=tmp_path, num_games=1)
    thief = PeerRuntime("thief", BASE / "config" / "thief", out_dir=tmp_path, num_games=1)
    thief.service.my_handshake = dict(thief.service.my_handshake,
                                      config_sha256="0" * 64)
    assert police.connect(DirectLink(thief.service)) is False
