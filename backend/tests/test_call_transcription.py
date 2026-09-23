from app.services import call_transcription


def test_transcribe_returns_none_when_unconfigured():
    assert call_transcription.settings.transcription_base_url is None
    assert call_transcription.transcribe("some/audio/ref") is None
