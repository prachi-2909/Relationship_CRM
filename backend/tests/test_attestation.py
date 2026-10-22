"""Device attestation endpoints + verifier logic (report-only by default)."""

import base64

from app.models.user import Role
from app.security import key_attestation


def _as(make_user, login, role, email):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def test_challenge_is_issued_and_single_use(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-attest@example.com")
    challenge = client.post("/api/v1/auth/attest/challenge").json()["challenge"]
    assert challenge
    # A challenge is consumed on first verify; a second verify with it is rejected as unknown.
    assert key_attestation._consume_challenge(challenge) is True
    assert key_attestation._consume_challenge(challenge) is False


def test_challenge_requires_authentication(client):
    assert client.post("/api/v1/auth/attest/challenge").status_code == 401


def test_verify_is_report_only_by_default(client, make_user, login):
    # No Google roots are provisioned, so the device is "not verified" - but with enforcement off the
    # endpoint still returns 200 and simply reports the verdict (never blocks the DC).
    _as(make_user, login, Role.DC, "dc-attest2@example.com")
    challenge = client.post("/api/v1/auth/attest/challenge").json()["challenge"]
    fake_cert = base64.b64encode(b"not-a-real-cert").decode()
    resp = client.post("/api/v1/auth/attest/verify", json={"challenge": challenge, "certificates": [fake_cert]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["attested"] is False
    assert body["enforced"] is False


def test_verify_blocks_when_enforcement_is_on(client, make_user, login, monkeypatch):
    from app.api.routes import attestation as attestation_route

    monkeypatch.setattr(attestation_route.settings, "require_device_attestation", True)
    _as(make_user, login, Role.DC, "dc-attest3@example.com")
    challenge = client.post("/api/v1/auth/attest/challenge").json()["challenge"]
    fake_cert = base64.b64encode(b"not-a-real-cert").decode()
    resp = client.post("/api/v1/auth/attest/verify", json={"challenge": challenge, "certificates": [fake_cert]})
    # With enforcement ON and no valid attestation, the device is refused.
    assert resp.status_code == 403


def test_verify_rejects_an_unissued_challenge(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-attest4@example.com")
    resp = client.post(
        "/api/v1/auth/attest/verify",
        json={"challenge": base64.b64encode(b"never-issued").decode(), "certificates": ["aGk="]},
    )
    assert resp.status_code == 200
    assert resp.json()["reason"] == "challenge unknown or expired"
