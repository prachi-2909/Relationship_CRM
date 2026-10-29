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


_SENT: list = []        # the (filename, bytes, content type) the fake endpoint last received


def _fake_whisper(monkeypatch, tmp_path, text):
    """Points transcribe() at a fake HTTP endpoint that answers with [text]."""
    _SENT.clear()
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
            _SENT.append(k["files"]["file"])
            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    return str(audio)


def test_the_audio_is_noise_reduced_before_it_is_sent(tmp_path, monkeypatch):
    ref = _fake_whisper(monkeypatch, tmp_path, "Haan ji, kiosk ka target is mahine pura ho jayega.")
    made = []

    def _fake_denoise(path):
        # Like the real one: a fresh temp file per call, which the caller deletes after reading it.
        out = tmp_path / f"cleaned{len(made)}.wav"
        out.write_bytes(b"CLEAN")
        made.append(out)
        return str(out)

    monkeypatch.setattr(call_transcription.settings, "transcription_denoise_enabled", True)
    monkeypatch.setattr(call_transcription, "_denoise_to_wav", _fake_denoise)
    assert call_transcription._denoised_upload("clip.ogg", b"RAW") == ("clip.wav", b"CLEAN")
    assert call_transcription.transcribe(ref) is not None
    assert _SENT == [("clip.wav", b"CLEAN", "audio/wav")]       # what actually went to Whisper
    assert not any(p.exists() for p in made)                    # temp files are cleaned up


def test_the_original_audio_is_sent_when_the_denoise_step_fails(monkeypatch):
    monkeypatch.setattr(call_transcription.settings, "transcription_denoise_enabled", True)

    def _boom(path):
        raise ImportError("No module named 'av'")      # e.g. PyAV missing from the image

    monkeypatch.setattr(call_transcription, "_denoise_to_wav", _boom)
    assert call_transcription._denoised_upload("clip.ogg", b"RAW") == ("clip.ogg", b"RAW")
    monkeypatch.setattr(call_transcription, "_denoise_to_wav", lambda path: None)
    assert call_transcription._denoised_upload("clip.ogg", b"RAW") == ("clip.ogg", b"RAW")


def test_the_denoise_step_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(call_transcription.settings, "transcription_denoise_enabled", False)

    def _must_not_run(path):
        raise AssertionError("denoise ran although it is switched off")

    monkeypatch.setattr(call_transcription, "_denoise_to_wav", _must_not_run)
    assert call_transcription._denoised_upload("clip.ogg", b"RAW") == ("clip.ogg", b"RAW")


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
