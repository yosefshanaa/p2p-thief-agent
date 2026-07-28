"""Gmail reporting: OAuth send-only scope, JSON attachments, mockable transport.

The report is never plaintext - it rides as a JSON attachment (#33-34), and
every send passes the Gatekeeper first. ``mode="draft"`` (dev default) files
a draft instead of sending; tests use the DryRunTransport.
"""

from __future__ import annotations

import base64
import json
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]  # least privilege (#30)


class DryRunTransport:
    """Test/dev transport: records what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def deliver(self, raw_b64: str, mode: str) -> dict[str, Any]:
        self.sent.append({"raw": raw_b64, "mode": mode})
        return {"id": f"dry-run-{len(self.sent)}"}


class GmailTransport:
    """Real Gmail API transport - only imported/used when credentials exist.

    Refreshes an expired access token via the long-lived refresh token and
    persists the renewal, so the agent stays autonomous for months (book
    Appendix A). The send-only scope cannot create drafts, so any mode other
    than "send" must be routed to the DryRunTransport by the caller.
    """

    def __init__(self, credentials_path: Path = Path("credentials.json"),
                 token_path: Path = Path("token.json")) -> None:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        self._service = build("gmail", "v1", credentials=creds)

    def deliver(self, raw_b64: str, mode: str) -> dict[str, Any]:
        if mode != "send":
            raise ValueError("send-only scope: non-send modes use DryRunTransport")
        return self._service.users().messages().send(
            userId="me", body={"raw": raw_b64}).execute()


def run_authorization(credentials_path: Path = Path("credentials.json"),
                      token_path: Path = Path("token.json"), *, port: int = 0) -> str:
    """One-time interactive OAuth consent (book Appendix A step E).

    Opens (or prints) the consent URL; on approval writes a fresh token.json
    with an access + refresh token pair. Needed once, and again whenever a
    Testing-mode refresh token expires (Google revokes those after ~7 days).
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=port, open_browser=True,
                                  authorization_prompt_message=
                                  "Open this URL to authorize gmail.send:\n{url}")
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return "token.json written (send-only scope)"


def build_report_email(*, to_addr: str, subject: str, body_text: str,
                       attachments: dict[str, dict[str, Any]]) -> str:
    """MIME message with each artifact attached as canonical JSON; returns base64url."""
    msg = MIMEMultipart()
    msg["to"], msg["subject"] = to_addr, subject
    msg.attach(MIMEText(body_text))
    for filename, payload in attachments.items():
        part = MIMEApplication(
            json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
            _subtype="json")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_report(*, transport: Any, gatekeeper: Any, to_addr: str, subject: str,
                attachments: dict[str, dict[str, Any]], mode: str) -> dict[str, Any]:
    """Gatekeeper-guarded delivery; a refused gate returns the reason, never raises."""
    verdict = gatekeeper.check()
    if verdict != "allowed":
        return {"delivered": False, "reason": verdict}
    raw = build_report_email(to_addr=to_addr, subject=subject,
                             body_text="Automated match report attached as JSON.",
                             attachments=attachments)
    receipt = transport.deliver(raw, mode)
    return {"delivered": True, "receipt": receipt, "mode": mode}
