from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _official(client, name: str) -> int:
    return client.post("/api/v1/officials", json={"name": name}).json()["id"]


def _rel(client, official_id: int) -> int:
    return client.post("/api/v1/relationships", json={"official_id": official_id}).json()["id"]


def test_manual_opportunity_lands_confirmed(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Asha Rao")
    rel = _rel(client, off)

    resp = client.post(
        "/api/v1/opportunities",
        json={"relationship_id": rel, "title": "New current account", "detail": "For their subsidiary"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["stage"] == "identified"
    assert body["source"] == "Manual entry"
    assert body["official_id"] == off


def test_interaction_creates_a_suggested_opportunity(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Ganesh Kumar")
    rel = _rel(client, off)

    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel,
            "type": "call",
            "raw_notes": "Ganesh mentioned he is interested in a new current account for his subsidiary.",
        },
    )

    listed = client.get("/api/v1/opportunities", params={"relationship_id": rel}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["status"] == "suggested"


def test_confirm_then_dismiss(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Bimal Sen")
    rel = _rel(client, off)
    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel,
            "type": "note",
            "raw_notes": "They are looking to expand their branch network next quarter.",
        },
    )
    opp = client.get("/api/v1/opportunities", params={"relationship_id": rel}).json()["items"][0]

    confirmed = client.patch(f"/api/v1/opportunities/{opp['id']}", json={"status": "confirmed"}).json()
    assert confirmed["status"] == "confirmed"

    dismissed = client.patch(f"/api/v1/opportunities/{opp['id']}", json={"status": "dismissed"}).json()
    assert dismissed["status"] == "dismissed"


def test_stage_change_requires_confirmation_first(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Kavita Nair")
    rel = _rel(client, off)
    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel,
            "type": "note",
            "raw_notes": "They are considering an upsell to a premium product.",
        },
    )
    opp = client.get("/api/v1/opportunities", params={"relationship_id": rel}).json()["items"][0]
    assert opp["status"] == "suggested"

    blocked = client.post(f"/api/v1/opportunities/{opp['id']}/stage", json={"stage": "qualified"})
    assert blocked.status_code == 422

    client.patch(f"/api/v1/opportunities/{opp['id']}", json={"status": "confirmed"})
    allowed = client.post(f"/api/v1/opportunities/{opp['id']}/stage", json={"stage": "qualified"})
    assert allowed.status_code == 200
    assert allowed.json()["stage"] == "qualified"


def test_winning_an_opportunity_sets_outcome_and_logs_activity(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Rohit Malhotra")
    rel = _rel(client, off)
    created = client.post(
        "/api/v1/opportunities", json={"relationship_id": rel, "title": "Term loan renewal"}
    ).json()

    won = client.post(
        f"/api/v1/opportunities/{created['id']}/stage",
        json={"stage": "won", "outcome_note": "Signed on Friday"},
    ).json()
    assert won["stage"] == "won"
    assert won["closed_at"] is not None
    assert won["outcome_note"] == "Signed on Friday"

    activities = client.get(f"/api/v1/opportunities/{created['id']}/activities").json()
    stage_changes = [a for a in activities if a["type"] == "stage_change"]
    assert len(stage_changes) == 1
    assert stage_changes[0]["from_stage"] == "identified"
    assert stage_changes[0]["to_stage"] == "won"


def test_manual_activity_log_rejects_stage_change_type(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Deepa Iyer")
    rel = _rel(client, off)
    created = client.post(
        "/api/v1/opportunities", json={"relationship_id": rel, "title": "New POS terminals"}
    ).json()

    rejected = client.post(
        f"/api/v1/opportunities/{created['id']}/activities",
        json={"type": "stage_change", "note": "trying to fake one"},
    )
    assert rejected.status_code == 422

    logged = client.post(
        f"/api/v1/opportunities/{created['id']}/activities",
        json={"type": "call", "note": "Discussed pricing"},
    )
    assert logged.status_code == 201
    assert logged.json()["type"] == "call"


def test_activity_log_requires_confirmation(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Neha Kapoor")
    rel = _rel(client, off)
    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel,
            "type": "note",
            "raw_notes": "Cross-sell opportunity for a new product line.",
        },
    )
    opp = client.get("/api/v1/opportunities", params={"relationship_id": rel}).json()["items"][0]

    blocked = client.post(
        f"/api/v1/opportunities/{opp['id']}/activities",
        json={"type": "note", "note": "should not work yet"},
    )
    assert blocked.status_code == 422


def test_repeated_detection_does_not_duplicate_the_same_title(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Vikram Shah")
    rel = _rel(client, off)
    note = "They are interested in a new current account for the branch."
    client.post(
        "/api/v1/interactions", json={"relationship_id": rel, "type": "call", "raw_notes": note}
    )
    client.post(
        "/api/v1/interactions", json={"relationship_id": rel, "type": "call", "raw_notes": note}
    )

    listed = client.get("/api/v1/opportunities", params={"relationship_id": rel}).json()
    assert listed["total"] == 1


def test_approver_viewer_can_read_but_not_create_or_decide(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Sanjay Gupta")
    rel = _rel(client, off)
    created = client.post(
        "/api/v1/opportunities", json={"relationship_id": rel, "title": "Working capital limit"}
    ).json()

    _as(make_user, login, Role.APPROVER_VIEWER, "viewer@example.com")
    assert client.get("/api/v1/opportunities").status_code == 200
    assert (
        client.post(
            "/api/v1/opportunities", json={"relationship_id": rel, "title": "Another one"}
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/v1/opportunities/{created['id']}/stage", json={"stage": "qualified"}).status_code
        == 403
    )
