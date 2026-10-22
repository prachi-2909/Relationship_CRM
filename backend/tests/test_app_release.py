from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def test_version_requires_auth(client):
    assert client.get("/api/v1/app/version").status_code == 401


def test_version_returns_configured_values(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-rel@example.com")
    resp = client.get("/api/v1/app/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_code"] >= 1
    assert body["download_url"].endswith("/app/download")


def test_download_404_when_nothing_published(client):
    resp = client.get("/api/v1/app/download")
    assert resp.status_code == 404
