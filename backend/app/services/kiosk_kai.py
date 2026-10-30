"""Kiosk KAI, read by the CRM: TARA's CSPs and figures, live.

Kiosk KAI (https://indev.eko.in/kiosk-kai/mcp) is one read-only MCP server over TARA, AutoGMap and the Kiosk
Application Form. The CRM signs in as its own Kiosk KAI user (`sbi-relationship-crm-app`), never as a person: its
calls are logged under that user, and a person's key must not be in this app, its .env or its containers.

Without KIOSK_KAI_APP_KEY nothing is called and call() returns None, so the CRM works from its own data exactly
as before. No tool returns a person's name, phone, email or message. Answers are kept for CACHE_MINUTES. Any
failure is logged (never with the key) and read as "no answer".
"""

from __future__ import annotations

import json
import logging
import time

from ..config import get_settings

logger = logging.getLogger("kiosk_kai")
settings = get_settings()

PROTOCOL = "2025-06-18"
TIMEOUT = 45.0
CACHE_MINUTES = 30
FAILURE_CACHE_MINUTES = 5          # a failure is remembered briefly so an outage does not slow every page
# Named in Kiosk KAI's audit log beside the app's user.
SKILL = "sbi-relationship-crm"

_cache: dict = {}


def _key() -> str:
    # A key typed or pasted on Windows can carry a hidden "\r" or spaces at its end, which breaks it.
    return (settings.kiosk_kai_app_key or "").strip()


def configured() -> bool:
    return bool(_key())


def _post(client, body: dict, session: str | None = None):
    headers = {
        "Authorization": f"Bearer {_key()}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    resp = client.post(settings.kiosk_kai_url, json=body, headers=headers)
    resp.raise_for_status()
    text = resp.text or ""
    if "event-stream" in resp.headers.get("content-type", ""):
        events = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        text = events[-1] if events else ""
    return resp.headers.get("mcp-session-id") or session, (json.loads(text) if text.strip() else None)


def _call(tool: str, arguments: dict) -> dict:
    import httpx

    with httpx.Client(timeout=TIMEOUT) as client:
        session, init = _post(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "sbi-relationship-crm", "version": "1"}}})
        if not init or "error" in init:
            raise RuntimeError(f"initialize refused: {(init or {}).get('error')}")
        _post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
        _, out = _post(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": tool, "arguments": {**arguments, "skill": SKILL}}}, session)
    if not out or "error" in out:
        raise RuntimeError(f"call refused: {(out or {}).get('error')}")
    result = out.get("result") or {}
    content = result.get("content") or []
    body = result.get("structuredContent") or (json.loads(content[0]["text"]) if content else None)
    if result.get("isError") or not isinstance(body, dict) or body.get("error"):
        raise RuntimeError(f"tool error: {str((body or {}).get('error') if isinstance(body, dict) else content)[:200]}")
    return body


def call(tool: str, **arguments) -> dict | None:
    """One tool's answer, {"data", "source", "as_of", "caveats", ...}, or None: no key, or Kiosk KAI did not answer.
    Kept for CACHE_MINUTES."""
    if not configured() or not settings.ai_data_processing_enabled:
        return None
    cache_key = (tool, json.dumps(arguments, sort_keys=True))
    hit = _cache.get(cache_key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        body = _call(tool, arguments)
    except Exception as exc:  # noqa: BLE001 - never let a Kiosk KAI problem break a CRM page
        logger.warning("kiosk_kai event=CALL_FAILED tool=%s error=%s: %s", tool, type(exc).__name__, str(exc)[:200])
        body = None
    _cache[cache_key] = (time.monotonic() + (CACHE_MINUTES if body else FAILURE_CACHE_MINUTES) * 60, body)
    return body
