"""Audio-to-text for call recordings and DC voice notes. Same real-endpoint-or-
stub shape as llm.py/embeddings.py - no specific vendor is hardwired; point
transcription_base_url at any OpenAI-compatible /audio/transcriptions endpoint
(Groq's hosted Whisper, a self-hosted Whisper server, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings

settings = get_settings()
logger = logging.getLogger("rcrm.call_transcription")

_CONTENT_TYPES = {
    ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".mp4": "audio/mp4",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".webm": "audio/webm",
    ".flac": "audio/flac", ".mpga": "audio/mpeg",
}


@dataclass
class TranscriptResult:
    text: str
    language: str | None = None
    confidence: float | None = None
    provider: str = "stub"


def _load_audio(audio_ref: str) -> tuple[str, bytes] | None:
    """audio_ref is either a local secure_object_ref (a voice note saved to
    disk) or a remote Knowlarity recording URL - resolve either into
    (filename, bytes) for upload."""
    if audio_ref.startswith("http://") or audio_ref.startswith("https://"):
        import httpx

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(audio_ref)
            resp.raise_for_status()
            name = Path(audio_ref.split("?")[0]).name or "recording.m4a"
            return name, resp.content
    path = Path(audio_ref)
    if not path.is_file():
        return None
    return path.name, path.read_bytes()


_local_model = None


def _looks_like_hallucination(text: str, prompt: str | None) -> bool:
    """Whisper on silent/garbage audio tends to (a) echo the seed prompt or (b) repeat one short
    phrase many times. Treat both as 'no usable speech' rather than a transcript."""
    t = text.strip().lower()
    if prompt and t == prompt.strip().lower():
        return True
    words = t.split()
    if len(words) >= 6:
        uniq = len(set(words))
        if uniq <= max(2, len(words) // 6):  # almost all words identical
            return True
    return False


def _get_local_model():
    """Lazy-loads the open-source faster-whisper model once (download on first use)."""
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel

        _local_model = WhisperModel(
            settings.local_whisper_model, device="cpu", compute_type=settings.local_whisper_compute
        )
    return _local_model


def _run_pass(model, path: str, *, language: str | None, task: str) -> str:
    """One Whisper decode. Returns cleaned text, or "" when the pass yields only
    silence/hallucination. Code-switched banking calls are decoded twice (a Hindi
    transcribe + an English translate) so the result is never an unreadable mix."""
    segments, _info = model.transcribe(
        path,
        language=language,
        task=task,
        beam_size=1,                       # greedy: much faster on CPU
        vad_filter=True,                   # drop non-speech (faster, avoids silence hallucination)
        condition_on_previous_text=False,  # stop the "repeat the same line" hallucination on noisy audio
        no_speech_threshold=0.6,           # treat low-confidence segments as silence, not words
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    # On silent/garbage audio Whisper tends to echo the prompt or repeat one phrase - drop those.
    if not text or _looks_like_hallucination(text, settings.transcription_prompt):
        return ""
    return text


def _denoise_to_wav(src_path: str) -> str | None:
    """Clean the call recording with a GENTLE, speech-safe filter chain before transcription, to
    lift transcription quality on noisy/quiet call audio. Uses PyAV's bundled libavfilter (no
    external ffmpeg needed). The chain only attenuates steady background noise and normalises
    loudness - it never gates or removes the voice, so a side of the call can't go silent:
      highpass 80 Hz (rumble) -> lowpass 8 kHz (hiss) -> afftdn (mild FFT denoise) -> dynaudnorm
      -> 16 kHz mono s16.
    Returns the path to a temp WAV, or None on any failure (caller then transcribes the original)."""
    import tempfile

    import av
    import av.filter

    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out.close()
    inc = outc = None
    try:
        inc = av.open(src_path)
        in_stream = inc.streams.audio[0]
        outc = av.open(out.name, "w")
        out_stream = outc.add_stream("pcm_s16le", rate=16000)

        graph = av.filter.Graph()
        abuf = graph.add_abuffer(template=in_stream)
        chain = [
            graph.add("highpass", "f=80"),
            graph.add("lowpass", "f=8000"),
            graph.add("afftdn", "nf=-25"),            # mild: -25 dB noise floor, keeps speech
            graph.add("dynaudnorm"),                  # loudness normalise, no hard clipping
            graph.add("aformat", "sample_fmts=s16:sample_rates=16000:channel_layouts=mono"),
        ]
        sink = graph.add("abuffersink")
        prev = abuf
        for node in chain + [sink]:
            prev.link_to(node)
            prev = node
        graph.configure()

        def _drain():
            while True:
                try:
                    frame = graph.pull()
                except (av.error.BlockingIOError, av.error.EOFError):
                    return
                frame.pts = None
                for pkt in out_stream.encode(frame):
                    outc.mux(pkt)

        for frame in inc.decode(in_stream):
            graph.push(frame)
            _drain()
        graph.push(None)
        _drain()
        for pkt in out_stream.encode():
            outc.mux(pkt)
        return out.name
    except Exception:
        logger.warning("audio denoise failed; transcribing the original", exc_info=True)
        try:
            os.unlink(out.name)
        except OSError:
            pass
        return None
    finally:
        if outc is not None:
            outc.close()
        if inc is not None:
            inc.close()


def _transcribe_local(audio_ref: str) -> TranscriptResult | None:
    """Open-source Whisper in-process - nothing leaves the server (DPDP-clean).

    Hindi-English calls are transcribed in TWO clearly-labelled sections: a native
    Hindi (Devanagari) pass and a separate English pass (Whisper's translate task),
    so the reviewer always gets one clean Hindi transcript and one clean English
    transcript instead of a single script-mixed jumble. The audio is first gently
    denoised (speech-safe) to improve quality - see _denoise_to_wav."""
    import os
    import tempfile

    loaded = _load_audio(audio_ref)
    if loaded is None:
        return None
    filename, audio_bytes = loaded
    suffix = Path(filename).suffix or ".m4a"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    denoised: str | None = None
    try:
        tmp.write(audio_bytes)
        tmp.close()
        # Gently clean the audio first; fall back to the raw file if denoise is unavailable.
        denoised = _denoise_to_wav(tmp.name) if settings.transcription_denoise_enabled else None
        audio_path = denoised or tmp.name
        model = _get_local_model()
        hindi = _run_pass(model, audio_path, language=settings.transcription_language or "hi", task="transcribe")
        english = _run_pass(model, audio_path, language=None, task="translate")
        sections: list[str] = []
        if hindi:
            sections.append(f"हिंदी (Hindi):\n{hindi}")
        if english:
            sections.append(f"English:\n{english}")
        if not sections:
            return None
        return TranscriptResult(
            text="\n\n".join(sections),
            language="hi+en" if hindi and english else ("hi" if hindi else "en"),
            provider=f"local-whisper-{settings.local_whisper_model}",
        )
    except Exception:
        logger.exception("local whisper transcription failed")
        return None
    finally:
        os.unlink(tmp.name)
        if denoised:
            try:
                os.unlink(denoised)
            except OSError:
                pass


def transcribe(audio_ref: str) -> TranscriptResult | None:
    """Transcribes an audio object by reference (a secure_object_ref/URL/path).
    Returns None when transcription is unavailable or fails - the caller records
    the call session as TRANSCRIPTION_FAILED and the DC can still fall back to
    manual text; this never blocks the pipeline.
    """
    if not settings.ai_data_processing_enabled:
        return None
    if settings.transcription_provider == "local_whisper":
        return _transcribe_local(audio_ref)
    if not settings.transcription_base_url:
        return None
    try:
        loaded = _load_audio(audio_ref)
        if loaded is None:
            return None
        filename, audio_bytes = loaded

        import httpx

        headers = {}
        if settings.transcription_api_key:
            headers["Authorization"] = f"Bearer {settings.transcription_api_key}"
        content_type = _CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")
        form: dict[str, str] = {"model": settings.transcription_model, "response_format": "verbose_json"}
        # Hinglish: pin the language and seed a romanized prompt so Hindi comes back in Latin script.
        if settings.transcription_language:
            form["language"] = settings.transcription_language
        if settings.transcription_prompt:
            form["prompt"] = settings.transcription_prompt
        with httpx.Client(timeout=settings.transcription_timeout_seconds) as client:
            resp = client.post(
                settings.transcription_base_url.rstrip("/") + "/audio/transcriptions",
                headers=headers,
                data=form,
                files={"file": (filename, audio_bytes, content_type)},
            )
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("text") or "").strip()
            if not text:
                return None
            return TranscriptResult(
                text=text,
                language=data.get("language"),
                provider=settings.transcription_model,
            )
    except Exception:
        logger.exception("transcription failed")
        return None
