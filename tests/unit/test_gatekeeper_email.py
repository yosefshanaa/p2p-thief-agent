"""Gatekeeper gates (quota / bucket / DOS) and the mockable Gmail sender."""

import base64

from p2p_pursuit.infra.email_sender import DryRunTransport, build_report_email, send_report
from p2p_pursuit.shared.gatekeeper import ALLOWED, BLOCKED_RATE, LOCKED_DOS, Gatekeeper
from p2p_pursuit.shared.rate_limiter import TokenBucket


def test_bucket_book_rule():
    now = {"t": 0.0}
    b = TokenBucket(capacity=5, refill_rate=0.8, clock=lambda: now["t"])
    for _ in range(5):
        assert b.allow()
    assert not b.allow()          # empty during the burst
    now["t"] = 1.3                # refill: 1.04 tokens
    assert b.allow()
    assert not b.allow()


def test_bucket_clamped_to_capacity():
    now = {"t": 0.0}
    b = TokenBucket(capacity=2, refill_rate=100, clock=lambda: now["t"])
    now["t"] = 60
    b.allow()
    assert b.tokens <= 2


def test_gatekeeper_rate_and_quota():
    now = {"t": 0.0}
    g = Gatekeeper(daily_quota=3, requests_per_minute=60, burst_capacity=2,
                   clock=lambda: now["t"])
    g.dos.max_in_window = 100  # isolate the rate gate
    assert g.check() == ALLOWED
    assert g.check() == ALLOWED
    assert g.check() == BLOCKED_RATE      # burst capacity 2 exhausted
    now["t"] = 2.0
    assert g.check() == ALLOWED           # refilled; third of quota
    now["t"] = 10.0
    assert g.check().startswith("rejected")  # daily quota (3) exhausted


def test_dos_lock_on_loop_bug():
    now = {"t": 0.0}
    g = Gatekeeper(daily_quota=1000, requests_per_minute=6000, burst_capacity=100,
                   clock=lambda: now["t"])
    verdicts = [g.check() for _ in range(12)]
    assert LOCKED_DOS in verdicts
    assert g.check() == LOCKED_DOS        # locked stays locked


def test_email_attachment_is_json():
    raw = build_report_email(to_addr="x@y.z", subject="s", body_text="b",
                             attachments={"result_g.json": {"a": 1}})
    decoded = base64.urlsafe_b64decode(raw).decode()
    assert 'filename="result_g.json"' in decoded
    assert "application/json" in decoded


def test_send_report_respects_gate_and_delivers():
    class DenyGate:
        def check(self):
            return "LOCKED: anomaly"

    class OpenGate:
        def check(self):
            return ALLOWED

    t = DryRunTransport()
    refused = send_report(transport=t, gatekeeper=DenyGate(), to_addr="a@b.c",
                          subject="s", attachments={"r.json": {}}, mode="send")
    assert refused == {"delivered": False, "reason": "LOCKED: anomaly"} and not t.sent
    sent = send_report(transport=t, gatekeeper=OpenGate(), to_addr="a@b.c",
                       subject="s", attachments={"r.json": {}}, mode="draft")
    assert sent["delivered"] and t.sent[0]["mode"] == "draft"


def test_a_read_only_token_mount_does_not_lose_the_report(tmp_path, monkeypatch):
    """A hosted peer gets its token as a read-only Secret Manager mount, and the
    access token expires hourly. Persisting the refresh is an optimisation - the
    credential is already live in memory - so an unguarded write would turn the
    routine refresh into the thing that loses the match report, the one artifact
    whose absence forfeits that side's points.
    """
    import sys
    import types

    from p2p_pursuit.infra import email_sender

    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")

    class Creds:
        expired, refresh_token = True, "r"

        def refresh(self, _request):
            self.expired = False

        def to_json(self):
            return "{}"

    def read_only_write(*_a, **_k):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(type(token), "write_text", read_only_write)
    fake_creds = types.ModuleType("google.oauth2.credentials")
    fake_creds.Credentials = types.SimpleNamespace(from_authorized_user_file=lambda *_a: Creds())
    fake_req = types.ModuleType("google.auth.transport.requests")
    fake_req.Request = lambda: None
    fake_disc = types.ModuleType("googleapiclient.discovery")
    fake_disc.build = lambda *_a, **_k: "service"
    for name, mod in (("google.oauth2.credentials", fake_creds),
                      ("google.auth.transport.requests", fake_req),
                      ("googleapiclient.discovery", fake_disc)):
        monkeypatch.setitem(sys.modules, name, mod)

    sender = email_sender.GmailTransport(tmp_path / "credentials.json", token)
    assert sender._service == "service", "a read-only mount must not stop the send"


def test_gmail_paths_follow_the_mount_a_hosted_peer_gets(monkeypatch, tmp_path):
    """Cloud Run mounts one secret per directory, so a hosted peer cannot keep
    token.json and credentials.json side by side in /app. The paths have to be
    addressable, exactly like the port and the opponent URL."""
    from p2p_pursuit.sdk.sdk import PursuitSDK

    creds, token = PursuitSDK.gmail_paths()
    assert (creds.name, token.name) == ("credentials.json", "token.json")

    monkeypatch.setenv("P2P_GMAIL_CREDENTIALS", str(tmp_path / "c" / "credentials.json"))
    monkeypatch.setenv("P2P_GMAIL_TOKEN", str(tmp_path / "t" / "token.json"))
    creds, token = PursuitSDK.gmail_paths()
    assert creds.parent != token.parent, "each secret gets its own mount directory"
    assert PursuitSDK().pick_email_transport("send", notify=lambda _m: None)


def test_a_missing_mounted_token_degrades_to_dry_run_not_a_crash(monkeypatch, tmp_path):
    """A report that raises is a forfeited report; one that falls back still
    writes the artifact."""
    from p2p_pursuit.infra.email_sender import DryRunTransport
    from p2p_pursuit.sdk.sdk import PursuitSDK

    monkeypatch.setenv("P2P_GMAIL_TOKEN", str(tmp_path / "absent" / "token.json"))
    assert isinstance(PursuitSDK().pick_email_transport("send", notify=lambda _m: None),
                      DryRunTransport)
