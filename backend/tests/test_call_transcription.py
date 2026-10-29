from app.services import call_transcription


def test_transcribe_returns_none_when_unconfigured():
    assert call_transcription.settings.transcription_base_url is None
    assert call_transcription.transcribe("some/audio/ref") is None


def test_kill_switch_blocks_transcription_even_when_configured(tmp_path, monkeypatch):
    # A configured endpoint is ignored while the DPDP master switch is off: nothing is sent.
    audio = tmp_path / "clip.m4a"
    audio.write_bytes(b"fake-audio")
    monkeypatch.setattr(call_transcription.settings, "transcription_base_url", "http://ai-host:8001/v1")
    monkeypatch.setattr(call_transcription.settings, "ai_data_processing_enabled", False)

    def _boom(*a, **k):  # the HTTP client must never be reached
        raise AssertionError("transcription endpoint was called while AI processing is disabled")

    monkeypatch.setattr(call_transcription, "_load_audio", _boom)
    assert call_transcription.transcribe(str(audio)) is None


def _fake_whisper(monkeypatch, tmp_path, text):
    """Points transcribe() at a fake HTTP endpoint that answers with [text]."""
    audio = tmp_path / "clip.ogg"
    audio.write_bytes(b"fake-audio")
    monkeypatch.setattr(call_transcription.settings, "transcription_provider", "openai")
    monkeypatch.setattr(call_transcription.settings, "transcription_base_url", "http://ai-host:8001/v1")
    monkeypatch.setattr(call_transcription.settings, "ai_data_processing_enabled", True)

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"text": text, "language": "hi"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    return str(audio)


def test_a_real_transcript_from_the_endpoint_is_accepted(tmp_path, monkeypatch):
    ref = _fake_whisper(monkeypatch, tmp_path, "Haan ji, kiosk ka target is mahine pura ho jayega.")
    result = call_transcription.transcribe(ref)
    assert result is not None and "target" in result.text


def test_a_transcript_that_just_loops_the_seed_prompt_is_rejected(tmp_path, monkeypatch):
    # What Whisper returned for a real call it could not make out: the prompt, over and over.
    junk = " ".join(["Haan ji, namaste. Banking call."] * 12)
    ref = _fake_whisper(monkeypatch, tmp_path, junk)
    assert call_transcription.transcribe(ref) is None


def test_a_transcript_equal_to_the_prompt_is_rejected(tmp_path, monkeypatch):
    ref = _fake_whisper(monkeypatch, tmp_path, call_transcription.settings.transcription_prompt)
    assert call_transcription.transcribe(ref) is None


def test_kill_switch_blocks_the_llm_even_when_configured(monkeypatch):
    from app.services import llm

    monkeypatch.setattr(llm.settings, "llm_base_url", "http://ai-host:8002/v1")
    monkeypatch.setattr(llm.settings, "ai_data_processing_enabled", False)
    assert llm.chat("system", "user") is None
