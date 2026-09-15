from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def test_admin_can_create_and_list_users(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.post(
        "/api/v1/users",
        json={
            "name": "New RM",
            "email": "newrm@example.com",
            "password": "secret123",
            "role": "relationship_manager",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "newrm@example.com"
    assert body["status"] == "active"
    assert "password" not in body and "password_hash" not in body

    listed = client.get("/api/v1/users").json()
    assert {u["email"] for u in listed} == {"admin@example.com", "newrm@example.com"}


def test_duplicate_email_is_rejected(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    client.post(
        "/api/v1/users",
        json={"name": "A", "email": "dup@example.com", "password": "secret123"},
    )
    resp = client.post(
        "/api/v1/users",
        json={"name": "B", "email": "dup@example.com", "password": "secret123"},
    )
    assert resp.status_code == 409


def test_non_admin_cannot_manage_users(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    assert client.get("/api/v1/users").status_code == 403
    assert (
        client.post(
            "/api/v1/users",
            json={"name": "X", "email": "x@example.com", "password": "secret123"},
        ).status_code
        == 403
    )


def test_admin_can_change_role_and_status(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    created = client.post(
        "/api/v1/users",
        json={"name": "New RM", "email": "newrm@example.com", "password": "secret123"},
    ).json()

    resp = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"role": "approver_viewer", "status": "disabled"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "approver_viewer"
    assert body["status"] == "disabled"


def test_disabled_user_cannot_log_in(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    created = client.post(
        "/api/v1/users",
        json={"name": "New RM", "email": "newrm@example.com", "password": "secret123"},
    ).json()
    client.patch(f"/api/v1/users/{created['id']}", json={"status": "disabled"})

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "newrm@example.com", "password": "secret123"},
    )
    assert resp.status_code in (401, 403)


def test_admin_can_reset_a_user_s_password(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    created = client.post(
        "/api/v1/users",
        json={"name": "New RM", "email": "newrm@example.com", "password": "oldpass123"},
    ).json()

    resp = client.post(
        f"/api/v1/users/{created['id']}/reset-password",
        json={"new_password": "brandnew123"},
    )
    assert resp.status_code == 200
    assert "password" not in resp.json()

    # old password no longer works, new one does
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "newrm@example.com", "password": "oldpass123"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "newrm@example.com", "password": "brandnew123"},
        ).status_code
        == 200
    )


def test_reset_password_requires_admin(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    created = client.post(
        "/api/v1/users",
        json={"name": "New RM", "email": "newrm@example.com", "password": "secret123"},
    ).json()

    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    resp = client.post(
        f"/api/v1/users/{created['id']}/reset-password",
        json={"new_password": "whatever123"},
    )
    assert resp.status_code == 403


def test_reset_password_for_unknown_user_is_404(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.post(
        "/api/v1/users/999999/reset-password", json={"new_password": "whatever123"}
    )
    assert resp.status_code == 404


def test_reset_password_enforces_minimum_length(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    created = client.post(
        "/api/v1/users",
        json={"name": "New RM", "email": "newrm@example.com", "password": "secret123"},
    ).json()
    resp = client.post(
        f"/api/v1/users/{created['id']}/reset-password", json={"new_password": "short"}
    )
    assert resp.status_code == 422
