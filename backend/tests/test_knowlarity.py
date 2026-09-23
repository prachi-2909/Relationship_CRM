from app.services import knowlarity


def test_click_to_call_returns_none_when_unconfigured():
    assert knowlarity.settings.knowlarity_base_url is None
    assert knowlarity.trigger_click_to_call("9876543210", "9123456780") is None


def test_fetch_recording_returns_none_when_unconfigured():
    assert knowlarity.fetch_recording_url("some-call-id") is None


def test_verify_webhook_rejects_without_secret():
    assert knowlarity.verify_webhook(provided_signature="abc", raw_body=b"{}") is False


def test_verify_webhook_rejects_without_signature(monkeypatch):
    monkeypatch.setattr(knowlarity.settings, "knowlarity_webhook_secret", "topsecret")
    assert knowlarity.verify_webhook(provided_signature=None, raw_body=b"{}") is False


def test_verify_webhook_accepts_correct_signature(monkeypatch):
    import hashlib
    import hmac

    monkeypatch.setattr(knowlarity.settings, "knowlarity_webhook_secret", "topsecret")
    body = b'{"call_id": "abc"}'
    sig = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert knowlarity.verify_webhook(provided_signature=sig, raw_body=body) is True


def test_verify_webhook_rejects_wrong_signature(monkeypatch):
    monkeypatch.setattr(knowlarity.settings, "knowlarity_webhook_secret", "topsecret")
    assert knowlarity.verify_webhook(provided_signature="wrong", raw_body=b"{}") is False
