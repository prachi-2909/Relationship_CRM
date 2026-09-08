from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def test_unit_types_seeded_and_require_auth(client, make_user, login):
    assert client.get("/api/v1/organization/unit-types").status_code == 401
    _as(make_user, login, Role.APPROVER_VIEWER, "v@example.com")
    resp = client.get("/api/v1/organization/unit-types")
    assert resp.status_code == 200
    codes = {t["code"] for t in resp.json()}
    assert {"HO", "RO", "ZO", "AO", "BRANCH"} <= codes


def test_only_admin_creates_units(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    resp = client.post(
        "/api/v1/organization/units",
        json={"name": "West RO", "type_code": "RO"},
    )
    assert resp.status_code == 403


def test_admin_builds_and_reads_tree(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")

    parent_a = client.post(
        "/api/v1/organization/units",
        json={"name": "West RO", "type_code": "RO"},
    ).json()
    child_a = client.post(
        "/api/v1/organization/units",
        json={"name": "Pune ZO", "type_code": "ZO", "parent_id": parent_a["id"]},
    ).json()
    client.post(
        "/api/v1/organization/units",
        json={"name": "FC Road Branch", "type_code": "BRANCH", "parent_id": child_a["id"]},
    )

    tree = client.get("/api/v1/organization/units/tree").json()
    assert len(tree) == 1
    assert tree[0]["name"] == "West RO"
    assert tree[0]["children"][0]["name"] == "Pune ZO"
    assert tree[0]["children"][0]["children"][0]["name"] == "FC Road Branch"


def test_unknown_type_is_rejected(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.post(
        "/api/v1/organization/units",
        json={"name": "Nowhere", "type_code": "ZONEX"},
    )
    assert resp.status_code == 422


def test_cannot_move_unit_under_itself(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    parent = client.post(
        "/api/v1/organization/units", json={"name": "P", "type_code": "RO"}
    ).json()
    child = client.post(
        "/api/v1/organization/units",
        json={"name": "C", "type_code": "ZO", "parent_id": parent["id"]},
    ).json()

    assert (
        client.patch(
            f"/api/v1/organization/units/{parent['id']}",
            json={"parent_id": parent["id"]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/organization/units/{parent['id']}",
            json={"parent_id": child["id"]},
        ).status_code
        == 422
    )


def test_archive_blocked_while_children_active(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    parent = client.post(
        "/api/v1/organization/units", json={"name": "P", "type_code": "RO"}
    ).json()
    client.post(
        "/api/v1/organization/units",
        json={"name": "C", "type_code": "ZO", "parent_id": parent["id"]},
    )
    resp = client.patch(
        f"/api/v1/organization/units/{parent['id']}", json={"status": "archived"}
    )
    assert resp.status_code == 409
