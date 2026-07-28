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
