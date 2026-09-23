"""Audio-to-text for call recordings and DC voice notes. Same real-endpoint-or-
stub shape as llm.py/embeddings.py - no specific vendor is hardwired; point
transcription_base_url at Sarvam AI, Bhashini, a self-hosted Whisper server,
or any OpenAI-compatible transcription endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import get_settings

settings = get_settings()
logger = logging.getLogger("rcrm.call_transcription")


@dataclass
class TranscriptResult:
    text: str
    language: str | None = None
    confidence: float | None = None
    provider: str = "stub"


def transcribe(audio_ref: str) -> TranscriptResult | None:
    """Transcribes an audio object by reference (a secure_object_ref/URL/path).
    Returns None when no transcription endpoint is configured or the call
    fails - the caller records the call session as TRANSCRIPTION_FAILED and
    the DC can still fall back to manual text; this never blocks the pipeline.
    """
    if not settings.transcription_base_url:
        return None
    try:
        import httpx

        headers = {}
        if settings.transcription_api_key:
            headers["Authorization"] = f"Bearer {settings.transcription_api_key}"
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                settings.transcription_base_url.rstrip("/") + "/transcribe",
                json={"audio_ref": audio_ref},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("text") or "").strip()
            if not text:
                return None
            return TranscriptResult(
                text=text,
                language=data.get("language"),
                confidence=data.get("confidence"),
                provider=settings.transcription_base_url,
            )
    except Exception:
        logger.exception("transcription failed")
        return None
