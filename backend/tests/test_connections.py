from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _official(client, name: str, level: str | None = None) -> int:
    return client.post("/api/v1/officials", json={"name": name, "level": level}).json()[
        "id"
    ]


def _rel(client, official_id: int) -> int:
    return client.post(
        "/api/v1/relationships", json={"official_id": official_id}
    ).json()["id"]


def test_manual_connection_is_confirmed_and_shows_on_both_officials(
    client, make_user, login
):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    a = _official(client, "Asha Rao", "AGM")
    b = _official(client, "Bimal Sen", "DGM")

    resp = client.post(
        "/api/v1/connections",
        json={"from_official_id": a, "to_official_id": b, "type": "reports_to"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["source"] == "Manual entry"

    # A reports to B
    ga = client.get(f"/api/v1/officials/{a}/connections").json()
    assert [n["label"] for n in ga["confirmed"]] == ["reports to Bimal Sen"]
    assert ga["confirmed"][0]["direction"] == "outgoing"

    # from B's side, A reports to them
    gb = client.get(f"/api/v1/officials/{b}/connections").json()
    assert gb["confirmed"][0]["direction"] == "incoming"
    assert gb["confirmed"][0]["label"] == "Asha Rao reports to them"


def test_works_with_is_undirected_and_deduped(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    a = _official(client, "Asha Rao")
    b = _official(client, "Bimal Sen")

    r1 = client.post(
        "/api/v1/connections",
        json={"from_official_id": a, "to_official_id": b, "type": "works_with"},
    )
    # same pair, opposite order, same type -> same row, not a second one
    r2 = client.post(
        "/api/v1/connections",
        json={"from_official_id": b, "to_official_id": a, "type": "works_with"},
    )
    assert r1.json()["id"] == r2.json()["id"]

    g = client.get(f"/api/v1/officials/{a}/connections").json()
    assert len(g["confirmed"]) == 1
    assert g["confirmed"][0]["direction"] == "mutual"


def test_self_connection_is_rejected(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    a = _official(client, "Asha Rao")
    resp = client.post(
        "/api/v1/connections",
        json={"from_official_id": a, "to_official_id": a, "type": "works_with"},
    )
    assert resp.status_code == 422


def test_viewer_cannot_create_but_can_read(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    a = _official(client, "Asha Rao")
    b = _official(client, "Bimal Sen")
    _as(make_user, login, Role.APPROVER_VIEWER, "viewer@example.com")
    denied = client.post(
        "/api/v1/connections",
        json={"from_official_id": a, "to_official_id": b, "type": "works_with"},
    )
    assert denied.status_code == 403
    assert client.get(f"/api/v1/officials/{a}/connections").status_code == 200


def test_interaction_comention_creates_suggested_edge_then_confirm(
    client, make_user, login
):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    ganesh = _official(client, "Ganesh Kumar", "GM")
    prachi = _official(client, "Prachi Sundaram", "AGM")
    rel = _rel(client, ganesh)

    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel,
            "type": "meeting",
            "raw_notes": "Reviewed the migration plan with Ms. Prachi Sundaram. "
            "She will send the revised schema by Monday.",
        },
    )

    g = client.get(f"/api/v1/officials/{ganesh}/connections").json()
    assert len(g["suggested"]) == 1
    edge = g["suggested"][0]
    assert edge["official_id"] == prachi
    assert edge["type"] == "works_with"
    assert "interaction" in edge["source"].lower()

    # confirming it moves it into the confirmed set, and it stays deduped
    conn_id = edge["connection_id"]
    patched = client.patch(
        f"/api/v1/connections/{conn_id}", json={"status": "confirmed"}
    )
    assert patched.status_code == 200 and patched.json()["status"] == "confirmed"

    g2 = client.get(f"/api/v1/officials/{ganesh}/connections").json()
    assert len(g2["suggested"]) == 0
    assert len(g2["confirmed"]) == 1


def test_brief_surfaces_confirmed_connections(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    a = _official(client, "Asha Rao", "AGM")
    b = _official(client, "Bimal Sen", "DGM")
    rel = _rel(client, a)

    before = client.get(f"/api/v1/relationships/{rel}/brief").json()
    assert before["stakeholders"]["available"] is False

    client.post(
        "/api/v1/connections",
        json={"from_official_id": a, "to_official_id": b, "type": "reports_to"},
    )
    after = client.get(f"/api/v1/relationships/{rel}/brief").json()
    sh = after["stakeholders"]
    assert sh["available"] is True
    assert sh["connections"][0]["name"] == "Bimal Sen"
    assert sh["connections"][0]["label"] == "reports to Bimal Sen"


def test_dismiss_then_recreate_keeps_one_row(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    a = _official(client, "Asha Rao")
    b = _official(client, "Bimal Sen")
    created = client.post(
        "/api/v1/connections",
        json={"from_official_id": a, "to_official_id": b, "type": "works_with"},
    ).json()
    client.patch(f"/api/v1/connections/{created['id']}", json={"status": "dismissed"})

    # asserting it again re-confirms the same row
    again = client.post(
        "/api/v1/connections",
        json={"from_official_id": a, "to_official_id": b, "type": "works_with"},
    )
    assert again.json()["id"] == created["id"]
    g = client.get(f"/api/v1/officials/{a}/connections").json()
    assert len(g["confirmed"]) == 1
