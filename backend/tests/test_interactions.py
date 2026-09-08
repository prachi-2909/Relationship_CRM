from app.models.user import Role


def _admin(make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")


def _relationship(client, name="A Rao"):
    official = client.post("/api/v1/officials", json={"name": name}).json()
    return client.post(
        "/api/v1/relationships", json={"official_id": official["id"]}
    ).json()


def test_logging_an_interaction_extracts_and_rescores(client, make_user, login):
    _admin(make_user, login)
    rel = _relationship(client)
    assert rel["score"] == 0

    resp = client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel["id"],
            "type": "meeting",
            "direction": "outbound",
            "raw_notes": "Good meeting at Head Office. They appreciated the update and "
            "will share revised targets by Monday.",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["sentiment"] == "positive"
    assert body["ai_summary"]
    assert body["ai_model"] == "stub"
    assert body["structured"]["commitments"]

    detail = client.get(f"/api/v1/relationships/{rel['id']}").json()
    assert detail["score"] > 0
    assert detail["last_interaction_at"] is not None

    history = client.get(f"/api/v1/relationships/{rel['id']}/score-history").json()
    assert any(h["reason"] == "interaction logged" for h in history)


def test_structured_override_survives_reprocess(client, make_user, login):
    _admin(make_user, login)
    rel = _relationship(client)
    created = client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel["id"],
            "type": "note",
            "raw_notes": "Spoke about pending settlement. Please expedite.",
        },
    ).json()
    iid = created["id"]

    override = {"topics": ["settlement"], "commitments": [], "requests": ["expedite settlement"], "people": []}
    patched = client.patch(
        f"/api/v1/interactions/{iid}",
        json={"structured": override, "sentiment": "neutral"},
    ).json()
    assert patched["structured"] == override
    assert patched["sentiment"] == "neutral"

    reprocessed = client.post(f"/api/v1/interactions/{iid}/reprocess").json()
    # AI output refreshed, but the human-edited effective data is untouched
    assert reprocessed["structured"] == override
    assert reprocessed["sentiment"] == "neutral"
    assert reprocessed["ai_structured"] is not None
    assert reprocessed["raw_notes"] == "Spoke about pending settlement. Please expedite."


def test_approver_cannot_log_interaction(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")
    rel = _relationship(client)

    make_user(email="v@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("v@example.com", "secret123")
    resp = client.post(
        "/api/v1/interactions",
        json={"relationship_id": rel["id"], "type": "note", "raw_notes": "hi"},
    )
    assert resp.status_code == 403


def test_list_interactions_filtered_by_relationship(client, make_user, login):
    _admin(make_user, login)
    rel_a = _relationship(client, "Officer A")
    rel_b = _relationship(client, "Officer B")
    for _ in range(3):
        client.post(
            "/api/v1/interactions",
            json={"relationship_id": rel_a["id"], "type": "call", "raw_notes": "call note"},
        )
    client.post(
        "/api/v1/interactions",
        json={"relationship_id": rel_b["id"], "type": "call", "raw_notes": "other"},
    )

    listed = client.get(
        "/api/v1/interactions", params={"relationship_id": rel_a["id"]}
    ).json()
    assert listed["total"] == 3
