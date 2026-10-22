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


def test_kill_switch_blocks_the_llm_even_when_configured(monkeypatch):
    from app.services import llm

    monkeypatch.setattr(llm.settings, "llm_base_url", "http://ai-host:8002/v1")
    monkeypatch.setattr(llm.settings, "ai_data_processing_enabled", False)
    assert llm.chat("system", "user") is None
