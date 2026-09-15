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
    assert {"CC", "LHO", "RBO", "AO", "BRANCH"} <= codes


def test_only_admin_creates_units(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    resp = client.post(
        "/api/v1/organization/units",
        json={"name": "West LHO", "type_code": "LHO"},
    )
    assert resp.status_code == 403


def test_admin_builds_and_reads_tree(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")

    parent_a = client.post(
        "/api/v1/organization/units",
        json={"name": "Corporate Centre", "type_code": "CC"},
    ).json()
    child_a = client.post(
        "/api/v1/organization/units",
        json={"name": "Pune RBO", "type_code": "RBO", "parent_id": parent_a["id"]},
    ).json()
    client.post(
        "/api/v1/organization/units",
        json={"name": "FC Road Branch", "type_code": "BRANCH", "parent_id": child_a["id"]},
    )

    tree = client.get("/api/v1/organization/units/tree").json()
    assert len(tree) == 1
    assert tree[0]["name"] == "Corporate Centre"
    assert tree[0]["children"][0]["name"] == "Pune RBO"
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
        "/api/v1/organization/units", json={"name": "P", "type_code": "CC"}
    ).json()
    child = client.post(
        "/api/v1/organization/units",
        json={"name": "C", "type_code": "RBO", "parent_id": parent["id"]},
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
        "/api/v1/organization/units", json={"name": "P", "type_code": "CC"}
    ).json()
    client.post(
        "/api/v1/organization/units",
        json={"name": "C", "type_code": "RBO", "parent_id": parent["id"]},
    )
    resp = client.patch(
        f"/api/v1/organization/units/{parent['id']}", json={"status": "archived"}
    )
    assert resp.status_code == 409


def test_only_the_top_level_type_can_be_created_without_a_parent(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    assert (
        client.post(
            "/api/v1/organization/units", json={"name": "Rootless LHO", "type_code": "LHO"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/organization/units", json={"name": "HQ", "type_code": "CC"}
        ).status_code
        == 201
    )


def test_child_type_must_rank_below_its_parent(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    lho = client.post(
        "/api/v1/organization/units", json={"name": "HQ", "type_code": "CC"}
    ).json()
    lho = client.post(
        "/api/v1/organization/units",
        json={"name": "West LHO", "type_code": "LHO", "parent_id": lho["id"]},
    ).json()

    # a Corporate Centre cannot be filed under an LHO - wrong direction
    resp = client.post(
        "/api/v1/organization/units",
        json={"name": "Bad", "type_code": "CC", "parent_id": lho["id"]},
    )
    assert resp.status_code == 422

    # an LHO cannot be filed under another LHO (same rank, not below it)
    resp = client.post(
        "/api/v1/organization/units",
        json={"name": "Also Bad", "type_code": "LHO", "parent_id": lho["id"]},
    )
    assert resp.status_code == 422


def test_hierarchy_allows_skipping_a_level(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    hq = client.post(
        "/api/v1/organization/units", json={"name": "HQ", "type_code": "CC"}
    ).json()
    # a Branch directly under Corporate Centre, with no LHO/RBO/AO in between
    resp = client.post(
        "/api/v1/organization/units",
        json={"name": "Direct Branch", "type_code": "BRANCH", "parent_id": hq["id"]},
    )
    assert resp.status_code == 201


def test_moving_a_unit_enforces_the_hierarchy_too(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    hq = client.post(
        "/api/v1/organization/units", json={"name": "HQ", "type_code": "CC"}
    ).json()
    branch = client.post(
        "/api/v1/organization/units",
        json={"name": "A Branch", "type_code": "BRANCH", "parent_id": hq["id"]},
    ).json()
    # promoting it to LHO while still parented under the (same-or-lower-rank) HQ is fine,
    # but re-typing it to CC while it has a parent is not - CC can only be root
    resp = client.patch(
        f"/api/v1/organization/units/{branch['id']}", json={"type_code": "CC"}
    )
    assert resp.status_code == 422
