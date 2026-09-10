from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _setup(client):
    official = client.post(
        "/api/v1/officials", json={"name": "Meera Iyer", "level": "AGM"}
    ).json()
    rel = client.post(
        "/api/v1/relationships", json={"official_id": official["id"]}
    ).json()
    return official, rel


def test_brief_has_the_five_answers(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    _, rel = _setup(client)

    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel["id"],
            "type": "meeting",
            "raw_notes": "Good review with the team. They were pleased and thanked us. "
            "I will send the revised numbers by Monday.",
        },
    )

    resp = client.get(f"/api/v1/relationships/{rel['id']}/brief")
    assert resp.status_code == 200
    body = resp.json()

    assert body["relationship_id"] == rel["id"]
    assert body["official_name"] == "Meera Iyer"
    assert body["what_is_important"]
    assert isinstance(body["what_changed"], list) and body["what_changed"]
    assert set(body["reconnect_opportunity"]) == {"yes", "reason"}
    assert body["next_interaction"]
    assert body["stakeholders"]["available"] is False
    assert body["narrative"]
    assert body["generated_by"] in ("template", "llm:stub") or body[
        "generated_by"
    ].startswith("llm:")


def test_brief_surfaces_the_open_commitment_as_next_step(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    _, rel = _setup(client)

    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel["id"],
            "type": "call",
            "raw_notes": "They asked for the pricing sheet. I will share the pricing "
            "sheet by tomorrow.",
        },
    )

    body = client.get(f"/api/v1/relationships/{rel['id']}/brief").json()
    assert body["recent_commitments"]
    assert "commitment" in body["next_interaction"].lower() or body["open_followups"]


def test_brief_requires_auth(client):
    resp = client.get("/api/v1/relationships/1/brief")
    assert resp.status_code == 401


def test_brief_404_for_unknown_relationship(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.get("/api/v1/relationships/9999/brief")
    assert resp.status_code == 404
