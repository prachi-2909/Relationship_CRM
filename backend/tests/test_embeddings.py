from app.services import embeddings


def test_empty_text_returns_none():
    assert embeddings.embed("") is None
    assert embeddings.embed("   ") is None


def test_stub_embedding_is_deterministic():
    a = embeddings.embed("The quarterly review went well.")
    b = embeddings.embed("The quarterly review went well.")
    assert a == b
    assert len(a) == embeddings.settings.embedding_dim


def test_stub_embedding_differs_for_different_text():
    a = embeddings.embed("Interested in a new working capital loan.")
    b = embeddings.embed("Birthday reminder for next week.")
    assert a != b


def test_remote_failure_falls_back_to_stub(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "embedding_base_url", "http://unreachable.invalid")

    def _boom(text, base_url):
        raise ConnectionError("no route")

    monkeypatch.setattr(embeddings, "_remote_embed", _boom)
    vector = embeddings.embed("hello world")
    assert vector == embeddings._stub_embed("hello world")


def test_no_endpoint_configured_uses_stub():
    assert embeddings.settings.embedding_base_url is None
    vector = embeddings.embed("hello world")
    assert vector == embeddings._stub_embed("hello world")
