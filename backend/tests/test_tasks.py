from datetime import datetime, timedelta, timezone

from app.models.user import Role


def _admin(make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")


def _relationship(client, name="A Rao"):
    official = client.post("/api/v1/officials", json={"name": name}).json()
    rel = client.post(
        "/api/v1/relationships", json={"official_id": official["id"]}
    ).json()
    # an admin-created relationship starts unowned; claim it so tasks have an assignee
    return client.post(f"/api/v1/relationships/{rel['id']}/claim").json()


def test_task_defaults_assignee_to_owner_and_rescores(client, make_user, login):
    _admin(make_user, login)
    me = client.get("/api/v1/auth/me").json()
    rel = _relationship(client)

    resp = client.post(
        "/api/v1/tasks",
        json={"relationship_id": rel["id"], "title": "Send September FI summary"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["assigned_to"] == me["id"]
    assert body["status"] == "open"
    assert body["official_name"]

    # a fresh open task means followup ratio 0/1 -> the signal is now active
    detail = client.get(f"/api/v1/relationships/{rel['id']}").json()
    assert "followup" in detail["score_components"]
    assert detail["score_components"]["followup"] == 0.0


def test_completing_a_task_lifts_followup(client, make_user, login):
    _admin(make_user, login)
    rel = _relationship(client)
    task = client.post(
        "/api/v1/tasks", json={"relationship_id": rel["id"], "title": "T1"}
    ).json()

    done = client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "done"})
    assert done.status_code == 200
    assert done.json()["completed_at"] is not None

    detail = client.get(f"/api/v1/relationships/{rel['id']}").json()
    assert detail["score_components"]["followup"] == 100.0


def test_overdue_list_and_sweep(client, make_user, login):
    _admin(make_user, login)
    rel = _relationship(client)
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    client.post(
        "/api/v1/tasks",
        json={"relationship_id": rel["id"], "title": "overdue one", "due_at": past},
    )
    client.post(
        "/api/v1/tasks",
        json={"relationship_id": rel["id"], "title": "future one", "due_at": future},
    )

    overdue = client.get("/api/v1/tasks/overdue").json()
    assert overdue["total"] == 1
    assert overdue["items"][0]["title"] == "overdue one"
    assert overdue["items"][0]["escalated_at"] is None

    swept = client.post("/api/v1/tasks/run-overdue-sweep")
    assert swept.status_code == 200
    assert swept.json()["escalated"] == 1

    again = client.get("/api/v1/tasks/overdue").json()
    assert again["items"][0]["escalated_at"] is not None

    # running twice does not double-escalate
    assert client.post("/api/v1/tasks/run-overdue-sweep").json()["escalated"] == 0


def test_task_from_commitment_links_interaction(client, make_user, login):
    _admin(make_user, login)
    rel = _relationship(client)
    interaction = client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel["id"],
            "type": "call",
            "raw_notes": "He will send the revised targets by Friday.",
        },
    ).json()

    task = client.post(
        "/api/v1/tasks",
        json={
            "relationship_id": rel["id"],
            "title": "Chase revised targets",
            "source_interaction_id": interaction["id"],
        },
    )
    assert task.status_code == 201
    assert task.json()["source_interaction_id"] == interaction["id"]


def test_approver_cannot_create_task(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")
    rel = _relationship(client)

    make_user(email="v@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("v@example.com", "secret123")
    resp = client.post(
        "/api/v1/tasks", json={"relationship_id": rel["id"], "title": "x"}
    )
    assert resp.status_code == 403


def test_only_admin_runs_sweep(client, make_user, login):
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    login("rm@example.com", "secret123")
    assert client.post("/api/v1/tasks/run-overdue-sweep").status_code == 403
