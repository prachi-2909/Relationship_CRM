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
    assert creates["items"][0]["actor_name"] == "Test User"
    assert creates["items"][0]["actor_role"] == "admin"
    # newest first
    assert all_logs["items"][0]["at"] >= all_logs["items"][-1]["at"]


def test_audit_log_filters_by_actor_role(client, make_user, login):
    make_user(email="admin2@example.com", password="secret123", role=Role.ADMIN)
    login("admin2@example.com", "secret123")
    dc = make_user(email="dc-audit@example.com", password="secret123", role=Role.DC)
    cc = client.post("/api/v1/organization/units", json={"name": "HQ", "type_code": "CC"}).json()
    client.post(
        "/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": cc["id"]}
    )
    client.post("/api/v1/auth/logout")
    login("dc-audit@example.com", "secret123")
    client.post(
        "/api/v1/officials", json={"name": "DC Added Official", "organization_unit_id": cc["id"]}
    )
    client.post("/api/v1/auth/logout")
    login("admin2@example.com", "secret123")

    dc_actions = client.get("/api/v1/audit-logs", params={"actor_role": "dc"}).json()
    assert dc_actions["total"] >= 1
    assert all(i["actor_role"] == "dc" for i in dc_actions["items"])
    assert any(i["action"] == "official.create" for i in dc_actions["items"])
