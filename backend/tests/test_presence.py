from app.models.user import Role


def test_heartbeat_and_background_toggle_foreground_flag(client, make_user, login):
    dc = make_user(email="presence-dc1@example.com", role=Role.DC, password="secret123")
    login("presence-dc1@example.com", "secret123")

    resp = client.post("/api/v1/presence/heartbeat")
    assert resp.status_code == 204

    make_user(email="presence-admin1@example.com", role=Role.ADMIN, password="secret123")
    login("presence-admin1@example.com", "secret123")
    status = {row["user_id"]: row for row in client.get("/api/v1/presence/status").json()}
    assert status[dc.id]["is_logged_in"] is True
    assert status[dc.id]["is_online"] is True
    assert status[dc.id]["last_active_at"] is not None

    login("presence-dc1@example.com", "secret123")
    resp = client.post("/api/v1/presence/background")
    assert resp.status_code == 204

    login("presence-admin1@example.com", "secret123")
    status = {row["user_id"]: row for row in client.get("/api/v1/presence/status").json()}
    assert status[dc.id]["is_online"] is False
    assert status[dc.id]["is_logged_in"] is True  # still logged in, just not in the foreground


def test_presence_status_is_admin_only(client, make_user, login):
    make_user(email="presence-dc2@example.com", role=Role.DC, password="secret123")
    login("presence-dc2@example.com", "secret123")
    resp = client.get("/api/v1/presence/status")
    assert resp.status_code == 403


def test_never_logged_in_user_is_not_online(client, make_user, login):
    dc = make_user(email="presence-dc3@example.com", role=Role.DC, password="secret123")
    make_user(email="presence-admin2@example.com", role=Role.ADMIN, password="secret123")
    login("presence-admin2@example.com", "secret123")
    status = {row["user_id"]: row for row in client.get("/api/v1/presence/status").json()}
    assert status[dc.id]["is_logged_in"] is False
    assert status[dc.id]["is_online"] is False
