from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _unit(client, name: str, type_code: str, parent_id: int | None = None) -> int:
    body = {"name": name, "type_code": type_code}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = client.post("/api/v1/organization/units", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_admin_assigns_and_removes_territory(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-terr@example.com")
    cc = _unit(client, "HQ", "CC")
    dc = make_user(email="dc-terr1@example.com", role=Role.DC)

    resp = client.post(
        "/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": cc}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["dc_user_id"] == dc.id
    assert body["organization_unit_id"] == cc

    listed = client.get(f"/api/v1/dc-territories?dc_user_id={dc.id}").json()
    assert len(listed) == 1

    resp = client.delete(f"/api/v1/dc-territories/{body['id']}")
    assert resp.status_code == 204
    listed = client.get(f"/api/v1/dc-territories?dc_user_id={dc.id}").json()
    assert listed == []


def test_only_admin_assigns_territory(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm-terr@example.com")
    resp = client.post(
        "/api/v1/dc-territories", json={"dc_user_id": 1, "organization_unit_id": 1}
    )
    assert resp.status_code == 403


def test_dc_without_territory_sees_no_officials(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-terr2@example.com")
    branch = _unit(client, "Some Branch", "CC")
    client.post("/api/v1/officials", json={"name": "Someone", "organization_unit_id": branch})
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-terr2@example.com")
    resp = client.get("/api/v1/officials")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_dc_sees_only_officials_in_their_territory_including_descendants(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-terr3@example.com")
    cc = _unit(client, "HQ2", "CC")
    branch_in = _unit(client, "In Territory Branch", "RBO", parent_id=cc)
    branch_out = _unit(client, "Out Of Territory Branch", "CC")

    in_official = client.post(
        "/api/v1/officials", json={"name": "Inside Person", "organization_unit_id": branch_in}
    ).json()
    client.post("/api/v1/officials", json={"name": "Outside Person", "organization_unit_id": branch_out})

    dc = make_user(email="dc-terr3@example.com", password="secret123", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": cc})
    client.post("/api/v1/auth/logout")

    login("dc-terr3@example.com", "secret123")
    resp = client.get("/api/v1/officials")
    names = {o["name"] for o in resp.json()["items"]}
    assert names == {"Inside Person"}

    # direct id access to an out-of-territory official is also blocked (AC-SEC-002 style)
    out_official = client.get(
        "/api/v1/officials", params={"q": "Outside"}
    )  # DC's own scoped search won't find it
    assert out_official.json()["items"] == []

    detail = client.get(f"/api/v1/officials/{in_official['id']}")
    assert detail.status_code == 200


def test_dc_cannot_access_official_outside_territory_by_id(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-terr4@example.com")
    cc = _unit(client, "HQ3", "CC")
    branch_out = _unit(client, "Elsewhere Branch", "CC")
    outside = client.post(
        "/api/v1/officials", json={"name": "Far Away Person", "organization_unit_id": branch_out}
    ).json()

    dc = make_user(email="dc-terr4@example.com", password="secret123", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": cc})
    client.post("/api/v1/auth/logout")

    login("dc-terr4@example.com", "secret123")
    resp = client.get(f"/api/v1/officials/{outside['id']}")
    assert resp.status_code == 404


def test_dc_can_create_and_edit_official_within_territory(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-terr5@example.com")
    cc = _unit(client, "HQ4", "CC")
    dc = make_user(email="dc-terr5@example.com", password="secret123", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": cc})
    client.post("/api/v1/auth/logout")

    login("dc-terr5@example.com", "secret123")
    resp = client.post(
        "/api/v1/officials", json={"name": "New Contact", "phone": "9876543210", "organization_unit_id": cc}
    )
    assert resp.status_code == 201, resp.text
    official_id = resp.json()["id"]

    resp = client.patch(f"/api/v1/officials/{official_id}", json={"designation": "Branch Manager"})
    assert resp.status_code == 200
    assert resp.json()["designation"] == "Branch Manager"


def test_dc_cannot_create_official_outside_territory(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-terr6@example.com")
    cc = _unit(client, "HQ5", "CC")
    other = _unit(client, "Other HQ", "CC")
    dc = make_user(email="dc-terr6@example.com", password="secret123", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": cc})
    client.post("/api/v1/auth/logout")

    login("dc-terr6@example.com", "secret123")
    resp = client.post(
        "/api/v1/officials", json={"name": "Bad Attempt", "organization_unit_id": other}
    )
    assert resp.status_code == 403


def test_dc_profile_self_and_admin_view(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-terr7@example.com")
    cc = _unit(client, "HQ6", "CC")
    dc = make_user(email="dc-terr7@example.com", password="secret123", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": cc})

    admin_view = client.get(f"/api/v1/dc/profile?dc_user_id={dc.id}")
    assert admin_view.status_code == 200
    assert len(admin_view.json()["territory"]) == 1
    client.post("/api/v1/auth/logout")

    login("dc-terr7@example.com", "secret123")
    self_view = client.get("/api/v1/dc/profile")
    assert self_view.status_code == 200
    assert self_view.json()["id"] == dc.id
