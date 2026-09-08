from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.engagement_moment import EngagementMoment, MomentStatus
from app.models.user import Role
from app.services import moments as moments_service


def _admin(make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")


def _active_relationship(client, name="A Rao"):
    official = client.post("/api/v1/officials", json={"name": name}).json()
    rel = client.post(
        "/api/v1/relationships", json={"official_id": official["id"]}
    ).json()
    client.post(f"/api/v1/relationships/{rel['id']}/claim")
    client.patch(f"/api/v1/relationships/{rel['id']}", json={"status": "active"})
    return official, rel


def _verified_date(client, official_id, kind, value):
    d = client.put(
        f"/api/v1/officials/{official_id}/dates/{kind}",
        json={"value": value, "source": "manual entry"},
    ).json()
    client.post(f"/api/v1/officials/{official_id}/dates/{d['id']}/verify")


def test_upcoming_birthday_creates_a_moment_with_evidence(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    soon = (date.today() + timedelta(days=3)).replace(year=1980)
    _verified_date(client, official["id"], "birthday", soon.isoformat())

    created = client.post("/api/v1/moments/detect").json()
    assert created["created"] == 1

    feed = client.get("/api/v1/moments", params={"type": "birthday"}).json()
    assert feed["total"] == 1
    moment = client.get(f"/api/v1/moments/{feed['items'][0]['id']}").json()
    assert moment["status"] == "detected"
    assert "birthday" in moment["evidence"]["trigger"]
    assert moment["evidence"]["relationship_band"]
    assert "days_since_last_interaction" in moment["evidence"]


def test_unverified_date_does_not_trigger(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    soon = (date.today() + timedelta(days=2)).replace(year=1980)
    client.put(
        f"/api/v1/officials/{official['id']}/dates/birthday",
        json={"value": soon.isoformat(), "source": "guess"},
    )  # not verified
    client.post("/api/v1/moments/detect")
    assert client.get("/api/v1/moments").json()["total"] == 0


def test_recent_contact_suppresses_the_moment(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    client.post(
        "/api/v1/interactions",
        json={"relationship_id": rel["id"], "type": "call", "raw_notes": "quick call"},
    )
    soon = (date.today() + timedelta(days=3)).replace(year=1980)
    _verified_date(client, official["id"], "birthday", soon.isoformat())

    client.post("/api/v1/moments/detect")
    moment = client.get("/api/v1/moments").json()["items"][0]
    assert moment["suppressed_reason"] is not None

    # cannot draft a suppressed moment without force
    blocked = client.post(f"/api/v1/moments/{moment['id']}/draft")
    assert blocked.status_code == 409
    forced = client.post(f"/api/v1/moments/{moment['id']}/draft", params={"force": "true"})
    assert forced.status_code == 200


def test_draft_approve_send_flow(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client, "Ravi Menon")
    recent = date.today() - timedelta(days=5)
    _verified_date(client, official["id"], "promoted", recent.isoformat())
    client.post("/api/v1/moments/detect")
    moment = client.get("/api/v1/moments", params={"type": "promotion"}).json()["items"][0]
    mid = moment["id"]

    drafted = client.post(f"/api/v1/moments/{mid}/draft").json()
    assert drafted["status"] == "draft_ready"
    assert "congratulations" in drafted["draft_text"].lower()

    edited = client.patch(
        f"/api/v1/moments/{mid}", json={"draft_text": "Dear Sir, congratulations."}
    ).json()
    assert edited["draft_text"] == "Dear Sir, congratulations."

    # approve requires a draft; send requires approval
    assert client.post(f"/api/v1/moments/{mid}/sent", json={}).status_code == 409
    approved = client.post(f"/api/v1/moments/{mid}/approve").json()
    assert approved["status"] == "approved"
    sent = client.post(
        f"/api/v1/moments/{mid}/sent", json={"outcome": "replied warmly"}
    ).json()
    assert sent["status"] == "sent_manually"
    assert sent["evidence"]["outcome"] == "replied warmly"


def test_inactivity_moment_becomes_a_task_on_approve(client, make_user, login, db):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    # push last_interaction_at far into the past
    from app.models.relationship import Relationship

    r = db.get(Relationship, rel["id"])
    r.last_interaction_at = datetime.now(timezone.utc) - timedelta(days=50)
    db.commit()

    client.post("/api/v1/moments/detect")
    moment = client.get("/api/v1/moments", params={"type": "inactivity"}).json()["items"][0]
    client.post(f"/api/v1/moments/{moment['id']}/draft")
    client.post(f"/api/v1/moments/{moment['id']}/approve")

    tasks = client.get(
        "/api/v1/tasks", params={"relationship_id": rel["id"]}
    ).json()
    assert any("check-in" in t["title"].lower() for t in tasks["items"])


def test_kill_switch_blocks_detection(client, make_user, login, monkeypatch):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    soon = (date.today() + timedelta(days=2)).replace(year=1980)
    _verified_date(client, official["id"], "birthday", soon.isoformat())

    monkeypatch.setattr(moments_service.settings, "enable_moments", False)
    resp = client.post("/api/v1/moments/detect")
    assert resp.status_code == 409
    assert client.get("/api/v1/moments").json()["total"] == 0


def test_approver_cannot_dismiss(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="v@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("admin@example.com", "secret123")
    official, rel = _active_relationship(client)
    recent = date.today() - timedelta(days=3)
    _verified_date(client, official["id"], "promoted", recent.isoformat())
    client.post("/api/v1/moments/detect")
    moment = client.get("/api/v1/moments").json()["items"][0]

    login("v@example.com", "secret123")
    assert (
        client.post(
            f"/api/v1/moments/{moment['id']}/dismiss", json={"reason": "no"}
        ).status_code
        == 403
    )


def test_no_send_endpoint_exists(client):
    # There is deliberately no route that transmits a message.
    paths = {r.path for r in client.app.routes}
    assert not any("send" in p and "moment" in p for p in paths)
