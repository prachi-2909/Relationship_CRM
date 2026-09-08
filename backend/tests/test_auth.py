from app.models.user import UserStatus


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
