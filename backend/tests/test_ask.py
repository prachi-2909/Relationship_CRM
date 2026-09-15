from app.models.relationship import Relationship
from app.models.user import Role, User
from app.services import portfolio
from app.services.supervisor import _match_officials


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


def test_ask_about_a_named_official_is_targeted(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    ganesh = _official(client, "Ganesh Kumar", "GM")
    rel = _rel(client, ganesh)
    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel,
            "type": "meeting",
            "raw_notes": "Good sync with Ganesh. He was pleased with the rollout.",
        },
    )

    resp = client.post("/api/v1/ask", json={"question": "What's going on with Ganesh Kumar?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "targeted"
    assert body["considered"] == [{"relationship_id": rel, "official_name": "Ganesh Kumar"}]
    assert body["answer"]
    assert body["generated_by"] in ("template",) or body["generated_by"].startswith("llm:")


def test_ask_generic_question_falls_back_to_portfolio(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Meera Iyer", "AGM")
    _rel(client, off)

    resp = client.post(
        "/api/v1/ask", json={"question": "What should I focus on this week?"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "portfolio"
    assert any(c["official_name"] == "Meera Iyer" for c in body["considered"])


def test_ask_with_no_data_says_so_plainly(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.post("/api/v1/ask", json={"question": "What should I do this week?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "portfolio"
    assert body["considered"] == []
    assert body["answer"]


def test_ask_requires_auth(client):
    resp = client.post("/api/v1/ask", json={"question": "Anything to flag?"})
    assert resp.status_code == 401


def test_ask_rejects_too_short_question(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.post("/api/v1/ask", json={"question": "hi"})
    assert resp.status_code == 422


def test_single_token_of_a_two_word_name_does_not_falsely_match(db, make_official):
    # "Kumar" alone is a common surname - one token hit on a two-word name
    # should not be treated as a confident match.
    make_official(name="Ganesh Kumar")
    matches = _match_officials(db, "Any updates on kumar this week?")
    assert matches == []
    matches_full = _match_officials(db, "Any updates on Ganesh Kumar this week?")
    assert [o.name for o in matches_full] == ["Ganesh Kumar"]


def test_portfolio_orders_worst_band_first(client, make_user, login, db):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    good = _official(client, "Strong Official")
    bad = _official(client, "Risky Official")
    good_rel_id = _rel(client, good)
    bad_rel_id = _rel(client, bad)

    db.query(Relationship).filter(Relationship.id == good_rel_id).update({"score": 90})
    db.query(Relationship).filter(Relationship.id == bad_rel_id).update({"score": 10})
    db.commit()

    admin = db.query(User).filter_by(email="admin@example.com").one()
    rows = portfolio.scan(db, admin)
    assert rows[0]["official_name"] == "Risky Official"
    assert rows[-1]["official_name"] == "Strong Official"


def test_portfolio_scopes_relationship_manager_to_own_book(client, make_user, login, db):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    mine = _official(client, "My Contact")
    other = _official(client, "Their Contact")
    _rel(client, mine)  # owned by admin by default via create-claims-it

    rm = make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    login("rm@example.com", "secret123")
    client.post("/api/v1/relationships", json={"official_id": other})  # RM claims this one

    rows = portfolio.scan(db, rm)
    assert [r["official_name"] for r in rows] == ["Their Contact"]
