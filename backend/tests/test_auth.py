from app.models.user import Role, UserStatus


def test_login_me_logout_cycle(client, make_user, login):
    make_user(email="ann@example.com", password="secret123", name="Ann")

    login("ann@example.com", "secret123")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ann@example.com"

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rejects_wrong_password(client, make_user):
    make_user(email="bob@example.com", password="correct-horse")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_login_rejects_disabled_account(client, make_user):
    make_user(
        email="gone@example.com",
        password="secret123",
        status=UserStatus.DISABLED,
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "gone@example.com", "password": "secret123"},
    )
    assert response.status_code == 403


def test_me_requires_authentication(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_locks_out_after_repeated_failures(client, make_user):
    make_user(email="brute@example.com", password="correct-horse")
    for _ in range(3):
        r = client.post("/api/v1/auth/login", json={"email": "brute@example.com", "password": "nope"})
        assert r.status_code == 401
    # 4th attempt is throttled - even the correct password is refused until the lockout clears.
    r = client.post("/api/v1/auth/login", json={"email": "brute@example.com", "password": "correct-horse"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_login_does_not_reveal_whether_an_email_exists(client, make_user):
    make_user(email="real@example.com", password="correct-horse")
    known = client.post("/api/v1/auth/login", json={"email": "real@example.com", "password": "wrong"})
    unknown = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "wrong"})
    # Same status and same message for a wrong password and a non-existent account.
    assert known.status_code == unknown.status_code == 401
    assert known.json()["detail"] == unknown.json()["detail"]


def test_logout_revokes_the_bearer_token(client, make_user):
    make_user(email="mobile@example.com", password="secret123")
    token = client.post(
        "/api/v1/auth/login", json={"email": "mobile@example.com", "password": "secret123"}
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=auth).status_code == 204
    # The bearer token must be dead after logout, not valid for its full lifetime.
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401


def test_password_reset_revokes_existing_sessions(client, make_user, login):
    make_user(email="admin-reset@example.com", password="secret123", role=Role.ADMIN)
    victim = make_user(email="victim@example.com", password="old-password")
    token = client.post(
        "/api/v1/auth/login", json={"email": "victim@example.com", "password": "old-password"}
    ).json()["token"]
    victim_auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=victim_auth).status_code == 200

    login("admin-reset@example.com", "secret123")
    assert client.post(
        f"/api/v1/users/{victim.id}/reset-password", json={"new_password": "brand-new-password"}
    ).status_code == 200
    # Drop the admin's session cookie the login fixture set, so the next request authenticates with
    # the victim's bearer token alone (a cookie would otherwise take precedence over the header).
    client.cookies.clear()
    # The victim's old session must stop working the moment their password is reset.
    assert client.get("/api/v1/auth/me", headers=victim_auth).status_code == 401
