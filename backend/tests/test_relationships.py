from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _official(client, name="A Rao", level=None):
    return client.post(
        "/api/v1/officials", json={"name": name, "level": level}
    ).json()


def test_manager_creating_relationship_claims_it(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    me = client.get("/api/v1/auth/me").json()
    official = _official(client, "Ravi Menon", "CGM")

    resp = client.post(
        "/api/v1/relationships", json={"official_id": official["id"]}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner_id"] == me["id"]
    # importance seeded from a leadership level
    assert body["importance"] == "strategic"
    assert body["score_components"]["_version"]


def test_one_relationship_per_official(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    official = _official(client, "Neha Singh")
    assert (
        client.post("/api/v1/relationships", json={"official_id": official["id"]}).status_code
        == 201
    )
    dup = client.post("/api/v1/relationships", json={"official_id": official["id"]})
    assert dup.status_code == 409


def test_approver_cannot_create_relationship(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")
    official = _official(client, "X")
    make_user(email="v@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("v@example.com", "secret123")
    resp = client.post("/api/v1/relationships", json={"official_id": official["id"]})
    assert resp.status_code == 403


def test_claim_unowned_then_blocked(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)

    login("admin@example.com", "secret123")
    official = _official(client, "Unowned One")
    rel = client.post(
        "/api/v1/relationships", json={"official_id": official["id"], "owner_id": None}
    ).json()
    assert rel["owner_id"] is None

    login("rm@example.com", "secret123")
    claimed = client.post(f"/api/v1/relationships/{rel['id']}/claim")
    assert claimed.status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert claimed.json()["owner_id"] == me["id"]

    again = client.post(f"/api/v1/relationships/{rel['id']}/claim")
    assert again.status_code == 409


def test_only_admin_reassigns_owner(client, make_user, login):
    admin = make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    rm = make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)

    login("rm@example.com", "secret123")
    official = _official(client, "Owned")
    rel = client.post(
        "/api/v1/relationships", json={"official_id": official["id"]}
    ).json()

    # owner (RM) may change status
    assert (
        client.patch(
            f"/api/v1/relationships/{rel['id']}", json={"status": "developing"}
        ).status_code
        == 200
    )
    # but not reassign
    assert (
        client.patch(
            f"/api/v1/relationships/{rel['id']}", json={"owner_id": admin.id}
        ).status_code
        == 403
    )

    login("admin@example.com", "secret123")
    assert (
        client.patch(
            f"/api/v1/relationships/{rel['id']}", json={"owner_id": rm.id}
        ).status_code
        == 200
    )


def test_list_filters_by_mine(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)

    login("admin@example.com", "secret123")
    o1 = _official(client, "Owned By Admin")
    client.post("/api/v1/relationships", json={"official_id": o1["id"]})

    login("rm@example.com", "secret123")
    o2 = _official(client, "Owned By RM")
    client.post("/api/v1/relationships", json={"official_id": o2["id"]})

    mine = client.get("/api/v1/relationships", params={"mine": "true"}).json()
    assert mine["total"] == 1
    assert mine["items"][0]["official_id"] == o2["id"]
