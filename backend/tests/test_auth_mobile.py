from app.models.user import Role


def _make(make_user, email="mobile@example.com", password="secret123", role=Role.DC):
    make_user(email=email, password=password, role=role)


def test_login_returns_token_in_body(client, make_user):
    _make(make_user)
    resp = client.post("/api/v1/auth/login", json={"email": "mobile@example.com", "password": "secret123"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["token"], str)
    assert len(body["token"]) > 10
    # cookie is still set for the web client, unchanged
    assert "rcrm_session" in resp.cookies


def test_bearer_token_authenticates(client, make_user):
    _make(make_user)
    resp = client.post("/api/v1/auth/login", json={"email": "mobile@example.com", "password": "secret123"})
    token = resp.json()["token"]
    client.cookies.clear()  # simulate a mobile client that never had the cookie

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "mobile@example.com"


def test_missing_bearer_prefix_is_rejected(client, make_user):
    _make(make_user)
    resp = client.post("/api/v1/auth/login", json={"email": "mobile@example.com", "password": "secret123"})
    token = resp.json()["token"]
    client.cookies.clear()
    me = client.get("/api/v1/auth/me", headers={"Authorization": token})
    assert me.status_code == 401


def test_invalid_bearer_token_is_rejected(client):
    client.cookies.clear()
    me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert me.status_code == 401


def test_cookie_auth_still_works_unchanged(client, make_user):
    _make(make_user, email="webuser@example.com")
    resp = client.post("/api/v1/auth/login", json={"email": "webuser@example.com", "password": "secret123"})
    assert resp.status_code == 200
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "webuser@example.com"
