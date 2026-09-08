from app.models.user import Role


def test_relationship_manager_cannot_list_users(client, make_user, login):
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    login("rm@example.com", "secret123")
    assert client.get("/api/v1/users").status_code == 403


def test_approver_cannot_create_users(client, make_user, login):
    make_user(email="view@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("view@example.com", "secret123")
    response = client.post(
        "/api/v1/users",
        json={"name": "X", "email": "x@example.com", "password": "secret123"},
    )
    assert response.status_code == 403


def test_admin_can_manage_users(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")

    created = client.post(
        "/api/v1/users",
        json={
            "name": "New Manager",
            "email": "new@example.com",
            "password": "secret123",
            "role": "relationship_manager",
        },
    )
    assert created.status_code == 201
    new_id = created.json()["id"]

    listing = client.get("/api/v1/users")
    assert listing.status_code == 200
    assert any(u["email"] == "new@example.com" for u in listing.json())

    patched = client.patch(f"/api/v1/users/{new_id}", json={"status": "disabled"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "disabled"


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/api/v1/users").status_code == 401
