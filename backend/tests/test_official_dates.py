from app.models.user import Role


def _admin(make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")


def test_set_verify_and_replace_birthday(client, make_user, login):
    _admin(make_user, login)
    official = client.post("/api/v1/officials", json={"name": "A Rao"}).json()
    oid = official["id"]

    put = client.put(
        f"/api/v1/officials/{oid}/dates/birthday",
        json={"value": "1975-09-12", "source": "manual entry", "confidence": 90},
    )
    assert put.status_code == 200
    assert put.json()["verification_status"] == "unverified"
    date_id = put.json()["id"]

    verified = client.post(f"/api/v1/officials/{oid}/dates/{date_id}/verify")
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "verified"

    # replacing the birthday resets verification and keeps a single row
    client.put(
        f"/api/v1/officials/{oid}/dates/birthday",
        json={"value": "1976-01-01", "source": "hr record"},
    )
    dates = client.get(f"/api/v1/officials/{oid}/dates").json()
    birthdays = [d for d in dates if d["kind"] == "birthday"]
    assert len(birthdays) == 1
    assert birthdays[0]["value"] == "1976-01-01"
    assert birthdays[0]["verification_status"] == "unverified"


def test_promoted_dates_accumulate(client, make_user, login):
    _admin(make_user, login)
    official = client.post("/api/v1/officials", json={"name": "B Singh"}).json()
    oid = official["id"]
    client.put(
        f"/api/v1/officials/{oid}/dates/promoted",
        json={"value": "2022-04-01", "source": "order 1"},
    )
    client.put(
        f"/api/v1/officials/{oid}/dates/promoted",
        json={"value": "2026-04-01", "source": "order 2"},
    )
    promoted = [
        d for d in client.get(f"/api/v1/officials/{oid}/dates").json()
        if d["kind"] == "promoted"
    ]
    assert len(promoted) == 2


def test_relationship_manager_cannot_verify_date(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    login("admin@example.com", "secret123")
    official = client.post("/api/v1/officials", json={"name": "C Iyer"}).json()
    d = client.put(
        f"/api/v1/officials/{official['id']}/dates/joined",
        json={"value": "2006-07-14", "source": "hr"},
    ).json()

    login("rm@example.com", "secret123")
    assert (
        client.post(
            f"/api/v1/officials/{official['id']}/dates/{d['id']}/verify"
        ).status_code
        == 403
    )
