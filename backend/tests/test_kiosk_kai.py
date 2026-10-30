import json
import logging

import pytest

from app.services import kiosk_kai

_SEEN: list = []


class _Resp:
    def __init__(self, payload, *, sse=False, session=None, status=200):
        self._payload = payload
        self.status_code = status
        self.headers = {"content-type": "text/event-stream" if sse else "application/json"}
        if session:
            self.headers["mcp-session-id"] = session

    @property
    def text(self):
        if self._payload is None:
            return ""
        body = json.dumps(self._payload)
        return f"event: message\ndata: {body}\n\n" if "event-stream" in self.headers["content-type"] else body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _server(monkeypatch, *, tool_result=None, tool_status=200, sse=False):
    """Replaces httpx.Client with a fake Kiosk KAI that records every request it receives."""
    _SEEN.clear()

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            _SEEN.append({"url": url, "json": json, "headers": headers})
            method = json.get("method")
            if method == "initialize":
                return _Resp({"jsonrpc": "2.0", "id": 1, "result": {}}, sse=sse, session="sess-1")
            if method == "notifications/initialized":
                return _Resp(None, sse=sse)
            result = tool_result if tool_result is not None else {
                "structuredContent": {"data": {"csps": 3}, "source": "tara", "as_of": "2026-10-30"}}
            return _Resp({"jsonrpc": "2.0", "id": 2, "result": result}, sse=sse, status=tool_status)

    monkeypatch.setattr("httpx.Client", _Client)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    kiosk_kai._cache.clear()
    monkeypatch.setattr(kiosk_kai.settings, "ai_data_processing_enabled", True)
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_url", "https://kai.example/mcp")
    yield
    kiosk_kai._cache.clear()


def test_without_a_key_nothing_is_called(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", None)

    def _boom(*a, **k):
        raise AssertionError("Kiosk KAI was called without a key")

    monkeypatch.setattr("httpx.Client", _boom)
    assert kiosk_kai.configured() is False
    assert kiosk_kai.call("tara.command_center") is None


def test_with_a_key_it_signs_in_and_returns_the_answer(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", "app-key")
    _server(monkeypatch)

    body = kiosk_kai.call("tara.my_csps", status="active", limit=50)

    assert body["as_of"] == "2026-10-30" and body["data"] == {"csps": 3}
    assert [r["json"].get("method") for r in _SEEN] == ["initialize", "notifications/initialized", "tools/call"]
    assert all(r["url"] == "https://kai.example/mcp" for r in _SEEN)
    assert all(r["headers"]["Authorization"] == "Bearer app-key" for r in _SEEN)
    assert _SEEN[1]["headers"]["Mcp-Session-Id"] == "sess-1"             # the session carries through
    params = _SEEN[2]["json"]["params"]
    assert params["name"] == "tara.my_csps"
    assert params["arguments"] == {"status": "active", "limit": 50, "skill": "sbi-relationship-crm"}


def test_the_answer_is_cached_so_a_page_reload_does_not_call_again(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", "app-key")
    _server(monkeypatch)
    kiosk_kai.call("tara.command_center")
    first_round = len(_SEEN)
    kiosk_kai.call("tara.command_center")
    assert len(_SEEN) == first_round                                       # served from the cache
    kiosk_kai.call("tara.command_center", period="2026-09")                # other arguments = another question
    assert len(_SEEN) > first_round


def test_a_hidden_carriage_return_or_space_in_the_key_is_stripped(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", "app-key\r\n ")
    _server(monkeypatch)
    kiosk_kai.call("tara.command_center")
    assert _SEEN[0]["headers"]["Authorization"] == "Bearer app-key"


def test_a_server_sent_event_reply_is_understood(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", "app-key")
    _server(monkeypatch, sse=True)
    assert kiosk_kai.call("tara.command_center")["source"] == "tara"


def test_a_failure_means_no_answer_and_never_leaks_the_key(monkeypatch, caplog):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", "super-secret-key")
    _server(monkeypatch, tool_status=401)
    with caplog.at_level(logging.WARNING, logger="kiosk_kai"):
        assert kiosk_kai.call("tara.command_center") is None
    assert "event=CALL_FAILED" in caplog.text and "tara.command_center" in caplog.text
    assert "super-secret-key" not in caplog.text


def test_a_tool_error_is_read_as_no_answer(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", "app-key")
    _server(monkeypatch, tool_result={"isError": True, "structuredContent": {"error": "not allowed"}})
    assert kiosk_kai.call("tara.command_center") is None


def test_nothing_is_called_while_the_ai_master_switch_is_off(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", "app-key")
    monkeypatch.setattr(kiosk_kai.settings, "ai_data_processing_enabled", False)
    monkeypatch.setattr("httpx.Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called while switched off")))
    assert kiosk_kai.call("tara.command_center") is None
