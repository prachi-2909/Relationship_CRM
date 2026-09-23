"""Knowlarity integration: outgoing Click-to-Call, recording retrieval, and
inbound webhook verification. Mirrors llm.py's shape - every function is a
graceful no-op/None when no account is configured, never a hard failure, so
the rest of the pipeline stays fully testable and demoable offline.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from ..config import get_settings

settings = get_settings()
logger = logging.getLogger("rcrm.knowlarity")


def trigger_click_to_call(dc_number: str, official_number: str) -> str | None:
    """Starts an outgoing call via Knowlarity's Click-to-Call API. Returns the
    Knowlarity call id, or None if no account is configured or the call
    could not be started - the caller falls back to a manual/voice-note flow.
    """
    if not (settings.knowlarity_base_url and settings.knowlarity_api_key and settings.knowlarity_number):
        return None
    try:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                settings.knowlarity_base_url.rstrip("/") + "/konnect/makecall/",
                params={
                    "api_key": settings.knowlarity_api_key,
                    "k_number": settings.knowlarity_number,
                    "agent_number": dc_number,
                    "customer_number": official_number,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            call_id = data.get("call_id") or data.get("id")
            return str(call_id) if call_id else None
    except Exception:
        logger.exception("knowlarity click-to-call failed")
        return None


def fetch_recording_url(knowlarity_call_id: str) -> str | None:
    """Fetches a signed/temporary recording URL for a completed call. None if
    unconfigured or the call has no recording available."""
    if not (settings.knowlarity_base_url and settings.knowlarity_api_key):
        return None
    try:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                settings.knowlarity_base_url.rstrip("/") + f"/calls/{knowlarity_call_id}/recording",
                headers={"Authorization": f"Bearer {settings.knowlarity_api_key}"},
            )
            resp.raise_for_status()
            return resp.json().get("recording_url")
    except Exception:
        logger.exception("knowlarity recording fetch failed")
        return None


def verify_webhook(*, provided_signature: str | None, raw_body: bytes) -> bool:
    """Constant-time check of a webhook's shared-secret signature. Without a
    configured secret, every webhook is rejected (fail closed) - the webhook
    receiver is only meaningful once a real Knowlarity account is wired up.
    """
    if not settings.knowlarity_webhook_secret or not provided_signature:
        return False
    expected = hmac.new(
        settings.knowlarity_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, provided_signature)
