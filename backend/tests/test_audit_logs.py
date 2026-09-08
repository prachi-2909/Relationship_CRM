from app.models.user import Role


def test_audit_log_viewer_is_admin_only(client, make_user, login):
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    login("rm@example.com", "secret123")
    assert client.get("/api/v1/audit-logs").status_code == 403


def test_audit_log_lists_and_filters(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")

    client.post("/api/v1/officials", json={"name": "Logged Official"})

    all_logs = client.get("/api/v1/audit-logs").json()
    assert all_logs["total"] >= 2  # auth.login + official.create

    creates = client.get(
        "/api/v1/audit-logs", params={"action": "official.create"}
    ).json()
    assert creates["total"] == 1
    assert creates["items"][0]["entity_type"] == "official"
    # newest first
    assert all_logs["items"][0]["at"] >= all_logs["items"][-1]["at"]
