from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def test_approver_cannot_create_official(client, make_user, login):
    _as(make_user, login, Role.APPROVER_VIEWER, "v@example.com")
    resp = client.post("/api/v1/officials", json={"name": "Smt. A. Rao"})
    assert resp.status_code == 403


def test_relationship_manager_creates_and_lists_officials(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")

    for name, level in [("A Rao", "DGM"), ("B Singh", "AGM"), ("C Iyer", "DGM")]:
        assert (
            client.post(
                "/api/v1/officials", json={"name": name, "level": level}
            ).status_code
            == 201
        )

    all_resp = client.get("/api/v1/officials").json()
    assert all_resp["total"] == 3

    dgm = client.get("/api/v1/officials", params={"level": "DGM"}).json()
    assert dgm["total"] == 2

    hit = client.get("/api/v1/officials", params={"q": "singh"}).json()
    assert hit["total"] == 1
    assert hit["items"][0]["name"] == "B Singh"


def test_set_field_then_admin_verify_rolls_up(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    official = client.post("/api/v1/officials", json={"name": "A Rao"}).json()
    oid = official["id"]

    set_resp = client.put(
        f"/api/v1/officials/{oid}/fields/designation",
        json={"value": "Deputy General Manager", "source": "Excel import 2026-09", "confidence": 80},
    )
    assert set_resp.status_code == 200
    body = set_resp.json()
    assert body["designation"] == "Deputy General Manager"
    assert body["fields"]["designation"]["verification_status"] == "unverified"
    assert body["verification_status"] == "unverified"

    verify_resp = client.post(f"/api/v1/officials/{oid}/fields/designation/verify")
    assert verify_resp.status_code == 200
    verified = verify_resp.json()
    assert verified["fields"]["designation"]["verification_status"] == "verified"
    assert verified["verification_status"] == "verified"


def test_admin_manual_entry_is_verified_on_create(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.post(
        "/api/v1/officials",
        json={
            "name": "Ravi Menon",
            "designation": "Regional Manager",
            "level": "AGM",
            "location": "Mumbai",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["verification_status"] == "verified"
    for field in ("designation", "level", "location"):
        assert body["fields"][field]["source"] == "Manual entry"
        assert body["fields"][field]["verification_status"] == "verified"
    # a field left blank has no provenance row
    assert "department" not in body["fields"]


def test_manager_manual_entry_waits_for_review(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    body = client.post(
        "/api/v1/officials", json={"name": "B Singh", "level": "DGM"}
    ).json()
    assert body["verification_status"] == "unverified"
    assert body["fields"]["level"]["source"] == "Manual entry"
    assert body["fields"]["level"]["verification_status"] == "unverified"


def test_relationship_manager_cannot_verify(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)

    login("admin@example.com", "secret123")
    official = client.post("/api/v1/officials", json={"name": "A Rao"}).json()
    client.put(
        f"/api/v1/officials/{official['id']}/fields/level",
        json={"value": "Scale VII", "source": "manual"},
    )

    login("rm@example.com", "secret123")
    resp = client.post(f"/api/v1/officials/{official['id']}/fields/level/verify")
    assert resp.status_code == 403


def test_verify_requires_the_field_to_be_set(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    official = client.post("/api/v1/officials", json={"name": "A Rao"}).json()
    resp = client.post(f"/api/v1/officials/{official['id']}/fields/location/verify")
    assert resp.status_code == 422


def test_editing_a_verified_field_resets_it(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    official = client.post("/api/v1/officials", json={"name": "A Rao"}).json()
    oid = official["id"]

    client.put(
        f"/api/v1/officials/{oid}/fields/location",
        json={"value": "Mumbai", "source": "manual"},
    )
    client.post(f"/api/v1/officials/{oid}/fields/location/verify")

    patched = client.patch(
        f"/api/v1/officials/{oid}", json={"location": "Pune"}
    ).json()
    assert patched["location"] == "Pune"
    assert patched["fields"]["location"]["verification_status"] == "unverified"
    assert patched["verification_status"] == "unverified"


def test_timeline_records_field_history(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    official = client.post("/api/v1/officials", json={"name": "A Rao"}).json()
    oid = official["id"]
    client.put(
        f"/api/v1/officials/{oid}/fields/designation",
        json={"value": "DGM", "source": "manual"},
    )
    client.post(f"/api/v1/officials/{oid}/fields/designation/verify")

    timeline = client.get(f"/api/v1/officials/{oid}/timeline").json()
    actions = [entry["action"] for entry in timeline]
    assert "official.create" in actions
    assert "official_field.set" in actions
    assert "official_field.verify" in actions
    # newest first
    assert actions.index("official_field.verify") < actions.index("official.create")
