import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

from app.models.call_intelligence import CallSession, CallSessionStatus, IdentityStatus
from app.models.interaction import Direction, Interaction
from app.models.relationship import Relationship
from app.models.user import Role
from app.services import call_intelligence as call_svc


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _official(client, name: str, phone: str | None = None) -> int:
    return client.post("/api/v1/officials", json={"name": name, "phone": phone}).json()["id"]


def _rel(client, official_id: int) -> int:
    return client.post("/api/v1/relationships", json={"official_id": official_id}).json()["id"]


# --- service-level -----------------------------------------------------------


def test_initiate_outgoing_call_without_knowlarity_configured(db, make_official, make_user):
    official = make_official(name="Outgoing Target", level="GM")
    official.phone = "9876543210"
    dc = make_user(email="dc1@example.com", role=Role.DC)
    db.commit()

    call = call_svc.initiate_outgoing_call(db, dc=dc, official=official)
    db.commit()

    assert call.channel == "manual"  # no Knowlarity account configured in tests
    assert call.knowlarity_call_id is None
    assert call.direction.value == "outbound"


def test_resolve_identity_matches_registered_official(db, make_official, make_user):
    official = make_official(name="Registered Official")
    official.phone = "9876543210"
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()

    call = CallSession(
        dc_user_id=make_user(email="dc2@example.com", role=Role.DC).id,
        direction=Direction.INBOUND, phone_ref="9876543210",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    status = call_svc.resolve_identity(db, call)
    assert status == IdentityStatus.REGISTERED
    assert call.official_id == official.id
    assert call.relationship_id == rel.id


def test_resolve_identity_unregistered_for_unknown_number(db, make_user):
    call = CallSession(
        dc_user_id=make_user(email="dc3@example.com", role=Role.DC).id,
        direction=Direction.INBOUND, phone_ref="9999999999", started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()
    status = call_svc.resolve_identity(db, call)
    assert status == IdentityStatus.UNREGISTERED
    assert call.official_id is None


def test_create_new_official_rejects_duplicate_phone(db, make_official, make_user):
    existing = make_official(name="Existing Official")
    existing.phone = "9876543210"
    dc = make_user(email="dc4@example.com", role=Role.DC)
    db.commit()

    call = CallSession(
        dc_user_id=dc.id, direction=Direction.INBOUND, phone_ref="9876543210", started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    with pytest.raises(ValueError, match="already exists"):
        call_svc.create_new_official(db, call, {"name": "Duplicate Attempt", "phone": "9876543210"}, dc)


def test_confirm_and_log_creates_exactly_one_interaction_without_reextraction(db, make_official, make_user):
    official = make_official(name="Confirm Target")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    dc = make_user(email="dc5@example.com", role=Role.DC)
    db.commit()

    call = CallSession(
        dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9876543210",
        official_id=official.id, relationship_id=rel.id, started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    brief = {"summary": "Discussed renewal.", "key_points": ["renewal"], "decisions": [],
              "commitments": [], "action_items": [], "opportunities": [], "relationship_signals": [],
              "suggested_next_interaction": ""}
    interaction = call_svc.confirm_and_log(db, call, dc, brief, "link")
    db.commit()

    assert interaction.structured == brief
    assert interaction.ai_summary == "Discussed renewal."
    assert interaction.ai_model is None  # _apply_extraction was NOT re-run
    assert call.processing_status == CallSessionStatus.CRM_LOGGED
    assert call.interaction_id == interaction.id

    count = db.query(Interaction).filter_by(id=interaction.id).count()
    assert count == 1


def test_confirm_and_log_requires_resolved_identity(db, make_user):
    dc = make_user(email="dc6@example.com", role=Role.DC)
    db.commit()
    call = CallSession(
        dc_user_id=dc.id, direction=Direction.INBOUND, phone_ref="9999999999", started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()
    with pytest.raises(ValueError, match="Resolve identity"):
        call_svc.confirm_and_log(db, call, dc, {}, "keep_unidentified")


# --- API / RBAC ---------------------------------------------------------------


def test_start_outgoing_call_via_api(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-api1@example.com")
    official_id = _official(client, "API Outgoing Target", phone="9876543210")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-api1@example.com")
    resp = client.post("/api/v1/calls/outgoing", json={"official_id": official_id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["direction"] == "outbound"
    assert body["processing_status"] == "initiated"


def test_dc_cannot_see_another_dcs_call(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-a@example.com")
    official_id = _official(client, "DC A Target", phone="9111111111")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-a@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-b@example.com")
    resp = client.get(f"/api/v1/calls/{call_id}")
    assert resp.status_code == 404

    resp = client.post(f"/api/v1/calls/{call_id}/manual-text", json={"text": "trying to peek"})
    assert resp.status_code == 404

    pending = client.get("/api/v1/calls/pending").json()
    assert all(c["id"] != call_id for c in pending["items"])


def test_admin_can_see_any_dcs_call(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-c-setup@example.com")
    official_id = _official(client, "DC C Target", phone="9222222222")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-c@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.ADMIN, "admin-cc@example.com")
    resp = client.get(f"/api/v1/calls/{call_id}")
    assert resp.status_code == 200


def test_approver_viewer_cannot_start_calls(client, make_user, login):
    _as(make_user, login, Role.APPROVER_VIEWER, "viewer-cc@example.com")
    resp = client.post("/api/v1/calls/outgoing", json={"official_id": 1})
    assert resp.status_code == 403


def test_manual_text_and_confirm_flow_via_api(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-flow-setup@example.com")
    official_id = _official(client, "Flow Target", phone="9333333333")
    _rel(client, official_id)  # confirm_and_log requires a resolved relationship
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-flow@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]

    resp = client.post(f"/api/v1/calls/{call_id}/manual-text", json={"text": "Had a good call about renewal."})
    assert resp.status_code == 200
    assert resp.json()["transcript_source"] == "manual_text"

    resp = client.post(
        f"/api/v1/calls/{call_id}/confirm",
        json={"brief": {"summary": "Renewal discussed"}, "identity_action": "link"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["processing_status"] == "crm_logged"


def test_identity_link_and_create_and_dismiss_via_api(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-identity-setup@example.com")
    unknown_call_official_id = _official(client, "Placeholder", phone="9000000000")
    existing_official_id = _official(client, "Link Target", phone="9444444444")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-identity@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": unknown_call_official_id}).json()["id"]

    resp = client.post(
        f"/api/v1/calls/{call_id}/identity/link",
        json={"official_id": existing_official_id, "update_phone": False},
    )
    assert resp.status_code == 200
    assert resp.json()["official_id"] == existing_official_id

    resp = client.post(f"/api/v1/calls/{call_id}/identity/dismiss")
    assert resp.status_code == 200
    assert resp.json()["identity_status"] == "unidentified"

    resp = client.post(
        f"/api/v1/calls/{call_id}/identity/create",
        json={"name": "Brand New Official", "phone": "9555555555"},
    )
    assert resp.status_code == 200
    assert resp.json()["identity_status"] == "verified_new_official"


# --- webhook -------------------------------------------------------------------


def test_webhook_rejects_missing_signature(client):
    resp = client.post("/api/v1/webhooks/knowlarity/call-completed", json={"call_id": "abc"})
    assert resp.status_code == 401


def test_webhook_accepts_valid_signature_and_creates_session(client, make_user, monkeypatch):
    from app.api.routes import call_intelligence as route_module

    monkeypatch.setattr(route_module.settings, "knowlarity_webhook_secret", "topsecret")
    dc = make_user(email="dc-webhook@example.com", role=Role.DC)

    payload = {
        "call_id": "kw-call-1", "direction": "incoming", "customer_number": "9876543210",
        "duration": 42, "dc_user_id": dc.id,
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()

    resp = client.post(
        "/api/v1/webhooks/knowlarity/call-completed",
        content=body,
        headers={"Content-Type": "application/json", "X-Knowlarity-Signature": sig},
    )
    assert resp.status_code == 204
