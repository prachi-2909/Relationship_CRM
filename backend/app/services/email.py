"""Email sending via Eko's Gmail Template Sender (MCP over HTTP).

The remote service wraps a plain-text message in a branded HTML template and delivers it through an
already-authorised Gmail account, so this module only needs the shared API key - no SMTP setup.
Nothing is sent unless gmail_mcp_api_key is configured; callers get a clear "not configured"
result instead of an exception, so a missing key never breaks a scheduled job.

MCP over HTTP is stateful: initialize -> notifications/initialized -> tools/call."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from ..config import get_settings

logger = logging.getLogger("rcrm.email")
settings = get_settings()


@dataclass
class EmailResult:
    ok: bool
    reason: str = ""


def is_configured() -> bool:
    return bool(settings.gmail_mcp_api_key and settings.gmail_mcp_url)


def _parse_mcp_response(resp) -> dict:
    """The endpoint may answer as JSON or as an SSE stream; pull the JSON-RPC object out of either."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[len("data:"):].strip())
                except json.JSONDecodeError:
                    continue
        return {}
    try:
        return resp.json()
    except Exception:
        return {}


def send_email(to: str, name: str, message: str, subject: str) -> EmailResult:
    """Send one templated email. Returns EmailResult(ok=...) - never raises, so a bad address or a
    transient error can't take a batch job down."""
    if not is_configured():
        return EmailResult(False, "Gmail sender not configured (set gmail_mcp_api_key)")
    if not to or "@" not in to:
        return EmailResult(False, f"invalid recipient: {to!r}")

    import httpx

    url = settings.gmail_mcp_url
    headers = {
        "X-API-Key": settings.gmail_mcp_api_key,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            init = client.post(url, headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "rcrm-backend", "version": "1"}},
            })
            init.raise_for_status()
            session_id = init.headers.get("mcp-session-id")
            if not session_id:
                return EmailResult(False, "no MCP session id returned")
            sess = {**headers, "mcp-session-id": session_id}
            client.post(url, headers=sess, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            call = client.post(url, headers=sess, json={
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "send_email", "arguments": {
                    "email": to, "name": name, "message": message, "subject": subject,
                    "sender_name": settings.smtp_from_name,
                }},
            })
            call.raise_for_status()
            data = _parse_mcp_response(call)
            if data.get("error"):
                return EmailResult(False, str(data["error"]))
            result = data.get("result", {})
            if result.get("isError"):
                return EmailResult(False, str(result.get("content")))
            return EmailResult(True)
    except Exception as exc:  # noqa: BLE001 - never propagate mail errors to the caller
        logger.warning("email send failed to %s: %s", to, exc)
        return EmailResult(False, str(exc))
