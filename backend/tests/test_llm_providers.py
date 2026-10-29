import logging

import httpx
import pytest

from app.services import llm

_SENT: dict = {}


def _fake_client(monkeypatch, *, reply: dict, status: int = 200):
    """Replaces httpx.Client with one that records the request and answers with [reply]."""
    _SENT.clear()

    class _Resp:
        status_code = status

        def raise_for_status(self):
            if status >= 400:
                raise httpx.HTTPStatusError("bad", request=None, response=None)

        def json(self):
            return reply

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            _SENT.update(url=url, json=json, headers=headers)
            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(llm.settings, "ai_data_processing_enabled", True)
    monkeypatch.setattr(llm.settings, "llm_base_url", "https://llm.example")
    monkeypatch.setattr(llm.settings, "llm_api_key", "secret-key")
    monkeypatch.setattr(llm.settings, "llm_model", "some-model")


def test_openai_compatible_endpoint_still_works(configured, monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "openai")
    _fake_client(monkeypatch, reply={"choices": [{"message": {"content": "hello"}}]})

    assert llm.chat("be brief", "hi") == "hello"
    assert _SENT["url"] == "https://llm.example/chat/completions"
    assert _SENT["headers"]["Authorization"] == "Bearer secret-key"
    assert _SENT["json"]["messages"][0] == {"role": "system", "content": "be brief"}


def test_anthropic_messages_api_is_called_in_its_own_format(configured, monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(llm.settings, "llm_base_url", "https://api.anthropic.com")
    _fake_client(monkeypatch, reply={"content": [{"type": "text", "text": "PMJJBY: 3 remaining"}]})

    out = llm.chat("be brief", "what is left?", history=[
        {"role": "user", "content": "earlier"}, {"role": "assistant", "content": "ok"},
    ])

    assert out == "PMJJBY: 3 remaining"
    assert _SENT["url"] == "https://api.anthropic.com/v1/messages"
    assert _SENT["headers"]["x-api-key"] == "secret-key"
    assert "Authorization" not in _SENT["headers"]
    assert _SENT["headers"]["anthropic-version"]
    body = _SENT["json"]
    assert body["system"] == "be brief"                       # top-level, not a message
    assert body["max_tokens"] > 0                             # required by the API
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert all(m["role"] != "system" for m in body["messages"])


def test_anthropic_reply_with_several_blocks_is_joined(configured, monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")
    _fake_client(monkeypatch, reply={"content": [
        {"type": "text", "text": '{"a": '}, {"type": "tool_use", "id": "x"}, {"type": "text", "text": "1}"},
    ]})
    assert llm.chat("s", "u") == '{"a": 1}'


def test_a_failing_endpoint_returns_none_and_says_why_in_the_log(configured, monkeypatch, caplog):
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")
    _fake_client(monkeypatch, reply={}, status=401)
    with caplog.at_level(logging.WARNING, logger="rcrm.llm"):
        assert llm.chat("s", "u") is None
    assert "LLM call failed" in caplog.text and "anthropic" in caplog.text


def test_nothing_is_sent_while_the_ai_master_switch_is_off(configured, monkeypatch):
    monkeypatch.setattr(llm.settings, "ai_data_processing_enabled", False)
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    def _boom(*a, **k):
        raise AssertionError("an LLM request was made while AI processing is disabled")

    monkeypatch.setattr("httpx.Client", _boom)
    assert llm.chat("s", "u") is None
