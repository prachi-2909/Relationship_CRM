import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

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


def test_submit_voice_note_saves_file_and_stays_reviewable(db, tmp_path, make_official, make_user, monkeypatch):
    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    official = make_official(name="Voice Note Target")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    dc = make_user(email="dc-voice1@example.com", role=Role.DC)
    db.commit()

    call = CallSession(
        dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9876543210",
        official_id=official.id, relationship_id=rel.id, started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    call_svc.submit_voice_note(db, call, audio_bytes=b"fake-audio-bytes", filename="note.m4a", actor=dc)
    db.commit()

    assert call.voice_note is not None
    assert call.voice_note.secure_object_ref
    # Transcription now runs in the background: right after upload there is no transcript yet and the
    # call is marked TRANSCRIBING, but it is already actionable (manual-text fallback stays open).
    assert call.transcript is None
    assert call.recording_status == CallSessionStatus.TRANSCRIBING
    assert call.processing_status == CallSessionStatus.REVIEW_REQUIRED


def test_voice_note_upload_via_api(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-voice-setup@example.com")
    official_id = _official(client, "Voice API Target", phone="9666666666")
    _rel(client, official_id)
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-voice2@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]

    resp = client.post(
        f"/api/v1/calls/{call_id}/voice-note",
        files={"file": ("note.m4a", b"fake-audio-bytes", "audio/mp4")},
    )
    assert resp.status_code == 200
    # Upload returns immediately with transcription pending (it runs in the background).
    assert resp.json()["recording_status"] == "transcribing"
    assert resp.json()["processing_status"] == "review_required"


def test_webhook_with_recording_but_no_transcription_endpoint_stays_reviewable(client, make_user, login, monkeypatch):
    from app.api.routes import call_intelligence as route_module

    monkeypatch.setattr(route_module.settings, "knowlarity_webhook_secret", "topsecret")
    # Recordings are only kept for CRM officials in the DC's territory.
    _crm_territory_with_official(client, make_user, login, dc_email="dc-webhook-rec@example.com", phone="9876543211")
    dc_id = client.get("/api/v1/auth/me").json()["id"]

    payload = {
        "call_id": "kw-call-rec-1", "direction": "incoming", "customer_number": "9876543211",
        "duration": 30, "dc_user_id": dc_id, "recording_url": "https://knowlarity.example/rec/1.mp3",
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    resp = client.post(
        "/api/v1/webhooks/knowlarity/call-completed",
        content=body,
        headers={"Content-Type": "application/json", "X-Knowlarity-Signature": sig},
    )
    assert resp.status_code == 204

    login("dc-webhook-rec@example.com", "secret123")
    call = client.get("/api/v1/calls/pending").json()["items"][0]
    assert call["recording_status"] == "recording"
    assert call["processing_status"] == "review_required"


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


def test_start_outgoing_call_with_manual_phone(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-manual1@example.com")
    resp = client.post("/api/v1/calls/outgoing", json={"phone": "9876500000"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["direction"] == "outbound"
    assert body["identity_status"] == "unidentified"


def test_start_outgoing_call_rejects_both_or_neither_target(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-manual2@example.com")
    assert client.post("/api/v1/calls/outgoing", json={}).status_code == 422
    assert client.post("/api/v1/calls/outgoing", json={"official_id": 1, "phone": "9876500000"}).status_code == 422


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


def test_dc_cannot_link_or_overwrite_an_out_of_territory_official(client, make_user, login):
    # Admin creates an official the DC has NO territory over, with a phone on file.
    _as(make_user, login, Role.ADMIN, "admin-link-guard@example.com")
    victim_branch = client.post(
        "/api/v1/organization/units", json={"name": "Other Branch", "type_code": "CC"}
    ).json()["id"]
    victim_id = client.post(
        "/api/v1/officials",
        json={"name": "Senior Official", "phone": "9000000001", "organization_unit_id": victim_branch},
    ).json()["id"]
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-link-guard@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"phone": "9000000099"}).json()["id"]

    # The DC tries to relabel their call as that official AND overwrite its number with their own.
    resp = client.post(
        f"/api/v1/calls/{call_id}/identity/link",
        json={"official_id": victim_id, "update_phone": True},
    )
    assert resp.status_code == 403

    # The victim official's phone must be untouched.
    client.post("/api/v1/auth/logout")
    _as(make_user, login, Role.ADMIN, "admin-link-check@example.com")
    assert client.get(f"/api/v1/officials/{victim_id}").json()["phone"] == "9000000001"


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
    # The link target is in a branch the DC covers - a DC may only link a call to (and relabel)
    # an official inside their own territory.
    branch = client.post(
        "/api/v1/organization/units", json={"name": "Identity Branch", "type_code": "CC"}
    ).json()["id"]
    existing_official_id = client.post(
        "/api/v1/officials", json={"name": "Link Target", "phone": "9444444444", "organization_unit_id": branch}
    ).json()["id"]
    dc = make_user(email="dc-identity@example.com", password="secret123", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": branch})
    client.post("/api/v1/auth/logout")

    login("dc-identity@example.com", "secret123")
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


# --- telephony provider abstraction --------------------------------------------


def test_telephony_provider_for_returns_knowlarity_by_default(monkeypatch):
    from app.services.telephony import telephony_provider_for
    from app.services.telephony.knowlarity_provider import KnowlarityTelephonyProvider

    monkeypatch.setattr(call_svc.settings, "telephony_provider", "knowlarity")
    assert isinstance(telephony_provider_for(call_svc.settings), KnowlarityTelephonyProvider)


def test_telephony_provider_for_returns_native_when_configured(monkeypatch):
    from app.services.telephony import telephony_provider_for
    from app.services.telephony.native_provider import NativeTelephonyProvider

    monkeypatch.setattr(call_svc.settings, "telephony_provider", "android_native")
    assert isinstance(telephony_provider_for(call_svc.settings), NativeTelephonyProvider)


def test_initiate_outgoing_call_native_mode_never_calls_knowlarity(db, make_official, make_user, monkeypatch):
    from app.services import knowlarity

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("Knowlarity must not be called in android_native mode")

    monkeypatch.setattr(call_svc.settings, "telephony_provider", "android_native")
    monkeypatch.setattr(knowlarity, "trigger_click_to_call", _must_not_be_called)

    official = make_official(name="Native Target")
    official.phone = "9876500000"
    dc = make_user(email="dc-native@example.com", role=Role.DC)
    db.commit()

    call = call_svc.initiate_outgoing_call(db, dc=dc, official=official)
    db.commit()

    assert call.channel == "android_native"
    assert call.knowlarity_call_id is None
    assert call.native_call_ref is None


def test_complete_native_call_not_connected_cancels_without_transcript(db, make_user):
    dc = make_user(email="dc-native-noconnect@example.com", role=Role.DC)
    call = CallSession(
        dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9876500001",
        channel="android_native", started_at=datetime.now(timezone.utc),
        processing_status=CallSessionStatus.INITIATED,
    )
    db.add(call)
    db.commit()

    call_svc.complete_native_call(
        db, call, actor=dc, ended_at=datetime.now(timezone.utc), duration_seconds=0, connected=False,
    )
    db.commit()

    assert call.processing_status == CallSessionStatus.CANCELLED
    assert call.transcript is None


def test_complete_native_call_connected_reaches_review_required_like_no_recording(db, make_official, make_user):
    official = make_official(name="Native Connected Target")
    official.phone = "9876500002"
    dc = make_user(email="dc-native-connect@example.com", role=Role.DC)
    call = CallSession(
        dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9876500002",
        channel="android_native", official_id=official.id, started_at=datetime.now(timezone.utc),
        processing_status=CallSessionStatus.INITIATED,
    )
    db.add(call)
    db.commit()

    call_svc.complete_native_call(
        db, call, actor=dc, ended_at=datetime.now(timezone.utc), duration_seconds=180, connected=True,
    )
    db.commit()

    assert call.recording_status == CallSessionStatus.NO_RECORDING
    assert call.processing_status == CallSessionStatus.REVIEW_REQUIRED
    assert call.duration_source == "device_estimated"


def test_native_complete_route_rejects_cross_dc_access(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-native-setup@example.com")
    official_id = _official(client, "Native Cross DC Target", phone="9876500003")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-native-a@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-native-b@example.com")
    resp = client.post(
        f"/api/v1/calls/{call_id}/native/complete",
        json={"ended_at": datetime.now(timezone.utc).isoformat(), "duration_seconds": 30, "connected": True},
    )
    assert resp.status_code == 404


def test_incoming_native_call_and_lookup_routes_via_api(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-native-incoming@example.com")
    now = datetime.now(timezone.utc)
    resp = client.post(
        "/api/v1/calls/native/incoming",
        json={
            "phone": "9876500004",
            "started_at": now.isoformat(),
            "ended_at": now.isoformat(),
            "duration_seconds": 60,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["channel"] == "android_native"
    assert body["direction"] == "inbound"
    assert body["processing_status"] == "review_required"

    resp = client.post("/api/v1/calls/lookup", json={"phone": "0000000000"})
    assert resp.status_code == 200
    # DC: not a CRM number -> no official and record_all is False (DC is CRM-gated).
    assert resp.json() == {"official": None, "record_all": False}


def test_call_timestamps_are_serialized_as_utc_with_offset(client, make_user, login):
    # SQLite returns naive datetimes; without an explicit UTC marker clients read them as
    # local time and show call start/end hours off.
    _as(make_user, login, Role.ADMIN, "admin-tz-setup@example.com")
    official_id = _official(client, "Timezone Target", phone="9876500009")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-tz@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]
    ended = datetime.now(timezone.utc).isoformat()
    client.post(
        f"/api/v1/calls/{call_id}/native/complete",
        json={"ended_at": ended, "duration_seconds": 12, "connected": True},
    )

    body = client.get(f"/api/v1/calls/{call_id}").json()
    for field in ("started_at", "ended_at"):
        assert body[field].endswith("Z") or body[field].endswith("+00:00"), (field, body[field])


def _incoming_payload(phone: str, started: datetime, seconds: int = 45, **extra) -> dict:
    return {
        "phone": phone,
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(seconds=seconds)).isoformat(),
        "duration_seconds": seconds,
        **extra,
    }


def test_native_call_log_supports_outbound_direction_and_manual_flag(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-native-dir@example.com")
    now = datetime.now(timezone.utc)

    resp = client.post(
        "/api/v1/calls/native/incoming",
        json=_incoming_payload("9876500011", now, direction="outbound", manual=True),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["direction"] == "outbound"
    assert body["duration_source"] == "manual"
    assert body["processing_status"] == "review_required"

    # Auto-detected (not manual) calls stay labeled as a device measurement.
    resp = client.post("/api/v1/calls/native/incoming", json=_incoming_payload("9876500012", now))
    assert resp.json()["duration_source"] == "device_estimated"
    assert resp.json()["direction"] == "inbound"


def test_native_call_log_dedupes_the_same_call_but_not_a_new_one(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-native-dedupe@example.com")
    now = datetime.now(timezone.utc)

    first = client.post("/api/v1/calls/native/incoming", json=_incoming_payload("9876500013", now)).json()

    # A retried upload / the same call seen twice: overlapping span, same number -> same session.
    again = client.post(
        "/api/v1/calls/native/incoming",
        json=_incoming_payload("9876500013", now + timedelta(seconds=5)),
    ).json()
    assert again["id"] == first["id"]

    # A second call placed shortly after the first one ENDED (first spans now..now+45s) is a
    # different call, even though its start is within a couple of minutes of the first.
    next_call = client.post(
        "/api/v1/calls/native/incoming",
        json=_incoming_payload("9876500013", now + timedelta(seconds=75)),
    ).json()
    assert next_call["id"] != first["id"]


def test_native_call_log_matches_an_in_app_call_whose_end_is_not_reported_yet(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-native-open@example.com")
    official_id = _official(client, "Open Call Target", phone="9876500014")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.DC, "dc-native-open@example.com")
    in_app = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()

    # The auto-detector reports that same call (dialed a moment after the session was created)
    # before the in-app tracker has reported its end: still the same call.
    detected = client.post(
        "/api/v1/calls/native/incoming",
        json=_incoming_payload("9876500014", datetime.now(timezone.utc) + timedelta(seconds=3), direction="outbound"),
    ).json()
    assert detected["id"] == in_app["id"]


def test_confirming_a_call_keeps_only_the_interaction(db, tmp_path, make_official, make_user, monkeypatch):
    """DPDP data minimisation: after logging, NOTHING of the call is kept in the call tables - no
    audio. The transcript and the AI brief stay (as does the CRM Interaction)."""
    from pathlib import Path

    from app.models.interaction import Interaction
    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    official = make_official(name="Audio Discard Target")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    dc = make_user(email="dc-discard@example.com", role=Role.DC)
    db.commit()
    call = CallSession(
        dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9876543211",
        official_id=official.id, relationship_id=rel.id, started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    call_svc.submit_voice_note(db, call, audio_bytes=b"fake-audio-bytes", filename="note.m4a", actor=dc)
    db.commit()
    audio_path = Path(call.voice_note.secure_object_ref)
    assert audio_path.exists()

    # Transcription isn't configured in tests, so supply the text the usual fallback way.
    call_svc.set_manual_text(db, call, "Discussed the renewal.", dc)
    db.refresh(call)  # the real /confirm request loads the call fresh; mirror that
    interaction = call_svc.confirm_and_log(db, call, dc, {"summary": "Renewal discussed"}, "link")
    db.commit()
    db.refresh(call)

    assert call.processing_status == CallSessionStatus.CRM_LOGGED
    # Only the audio is gone: the stored file, the voice-note row and any provider recording reference.
    assert call.voice_note is None
    assert call.recording is None
    assert not audio_path.exists()
    assert call.recording_status == CallSessionStatus.PURGED
    # The transcript and the AI brief are kept.
    assert call.transcript is not None and "renewal" in call.transcript.text.lower()
    assert call.analysis is not None
    # ...and so is the CRM Interaction.
    kept = db.get(Interaction, interaction.id)
    assert kept is not None and "renewal" in kept.raw_notes.lower()


def test_rm_call_recording_is_kept_after_logging(db, tmp_path, make_official, make_user, monkeypatch):
    """RM policy (opposite of DC): a Relationship Manager's recording + transcript are KEPT in the
    call tables after the call is logged, not discarded - the business retains them."""
    from pathlib import Path

    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    official = make_official(name="RM Keep Target")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    rm = make_user(email="rm-keep@example.com", role=Role.RELATIONSHIP_MANAGER)
    db.commit()
    call = CallSession(
        dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9876543212",
        official_id=official.id, relationship_id=rel.id, started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    call_svc.submit_voice_note(db, call, audio_bytes=b"fake-audio-bytes", filename="note.m4a", actor=rm)
    db.commit()
    audio_path = Path(call.voice_note.secure_object_ref)
    assert audio_path.exists()

    call_svc.set_manual_text(db, call, "Discussed the target.", rm)
    db.refresh(call)
    call_svc.confirm_and_log(db, call, rm, {"summary": "Target discussed"}, "link")
    db.commit()
    db.refresh(call)

    assert call.processing_status == CallSessionStatus.CRM_LOGGED
    # RM recording + transcript are retained, and the audio file still exists on disk.
    assert call.voice_note is not None
    assert call.transcript is not None
    assert audio_path.exists()


def test_rm_records_only_csp_numbers(client, db, make_user, login):
    """An RM records a call only when the number is a CSP's (primary or alternate); a personal
    number comes back record_all=False, a CSP number record_all=True."""
    from app.models.csp import Csp, CspStatus

    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm-lookup@example.com")
    db.add(Csp(
        csp_id="LK1", name="CSP LK", rm_name="X", mobile="9888800001",
        alternate_mobile="9888800002", status=CspStatus.ACTIVE,
    ))
    db.commit()

    # A personal / unknown number: not recorded.
    r1 = client.post("/api/v1/calls/lookup", json={"phone": "0000000000"})
    assert r1.json() == {"official": None, "record_all": False}
    # The CSP's primary number: recorded.
    r2 = client.post("/api/v1/calls/lookup", json={"phone": "9888800001"})
    assert r2.json()["record_all"] is True
    # The CSP's ALTERNATE number: also recorded.
    r3 = client.post("/api/v1/calls/lookup", json={"phone": "9888800002"})
    assert r3.json()["record_all"] is True


def test_rm_stale_call_audio_is_not_purged(db, tmp_path, make_official, make_user, monkeypatch):
    """The nightly retention sweep purges unlogged DC audio, but never an RM's."""
    from datetime import timedelta
    from pathlib import Path

    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    rm = make_user(email="rm-purge@example.com", role=Role.RELATIONSHIP_MANAGER)
    db.commit()
    call = CallSession(
        dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9876543213",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()
    call_svc.submit_voice_note(db, call, audio_bytes=b"fake-audio-bytes", filename="note.m4a", actor=rm)
    db.commit()
    audio_path = Path(call.voice_note.secure_object_ref)

    # Run the sweep with a cutoff far in the future so the note counts as "stale".
    purged = call_svc.purge_stale_call_audio(db, now=datetime.now(timezone.utc) + timedelta(days=3650))
    db.commit()
    db.refresh(call)
    assert purged == 0
    assert call.voice_note is not None
    assert audio_path.exists()


def test_audio_file_survives_a_rolled_back_logging(db, tmp_path, make_official, make_user, monkeypatch):
    """The file goes only once the row's deletion is committed - never a row pointing at nothing."""
    from pathlib import Path

    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    official = make_official(name="Audio Rollback Target")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    dc = make_user(email="dc-rollback@example.com", role=Role.DC)
    db.commit()
    call = CallSession(
        dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9876543212",
        official_id=official.id, relationship_id=rel.id, started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()

    call_svc.submit_voice_note(db, call, audio_bytes=b"fake-audio-bytes", filename="note.m4a", actor=dc)
    db.commit()
    audio_path = Path(call.voice_note.secure_object_ref)
    call_svc.set_manual_text(db, call, "Rolled back.", dc)
    call_svc.confirm_and_log(db, call, dc, {"summary": "x"}, "link")
    db.rollback()

    assert audio_path.exists()


def _crm_territory_with_official(client, make_user, login, *, dc_email: str, phone: str) -> int:
    """Admin sets up a branch, an official with [phone] in it and a DC covering it; leaves the DC logged in."""
    _as(make_user, login, Role.ADMIN, f"admin-{dc_email}")
    branch = client.post(
        "/api/v1/organization/units", json={"name": f"Branch {dc_email}", "type_code": "CC"}
    ).json()["id"]
    official_id = client.post(
        "/api/v1/officials", json={"name": f"Official {phone}", "phone": phone, "organization_unit_id": branch}
    ).json()["id"]
    _rel(client, official_id)
    dc = make_user(email=dc_email, password="secret123", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": branch})
    client.post("/api/v1/auth/logout")
    login(dc_email, "secret123")
    return official_id


def _upload_call_recording(client, call_id: int):
    return client.post(
        f"/api/v1/calls/{call_id}/voice-note",
        files={"file": ("callrec.m4a", b"fake-audio-bytes", "audio/mp4")},
        data={"kind": "call_recording"},
    )


def test_call_recording_accepted_for_a_crm_official_in_territory(client, make_user, login, tmp_path, monkeypatch):
    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    official_id = _crm_territory_with_official(
        client, make_user, login, dc_email="dc-rec-ok@example.com", phone="9811100001"
    )
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]

    resp = _upload_call_recording(client, call_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["has_voice_note"] is True


def test_call_recording_rejected_for_a_number_not_in_the_crm(client, make_user, login, tmp_path, monkeypatch):
    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    _crm_territory_with_official(client, make_user, login, dc_email="dc-rec-no@example.com", phone="9811100002")
    call_id = client.post("/api/v1/calls/outgoing", json={"phone": "9811199999"}).json()["id"]

    resp = _upload_call_recording(client, call_id)
    assert resp.status_code == 403
    assert list(tmp_path.rglob("*.m4a")) == []
    assert client.get(f"/api/v1/calls/{call_id}").json()["has_voice_note"] is False

    # The DC's own recap of that same call is still allowed - it isn't a recording of the call.
    resp = client.post(
        f"/api/v1/calls/{call_id}/voice-note",
        files={"file": ("voicenote.m4a", b"fake-audio-bytes", "audio/mp4")},
    )
    assert resp.status_code == 200


def test_call_recording_rejected_for_a_crm_official_outside_territory(client, make_user, login, tmp_path, monkeypatch):
    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    _as(make_user, login, Role.ADMIN, "admin-rec-far@example.com")
    official_id = _official(client, "Far Official", phone="9811100003")
    _rel(client, official_id)
    client.post("/api/v1/auth/logout")
    _as(make_user, login, Role.DC, "dc-rec-far@example.com")
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]

    assert _upload_call_recording(client, call_id).status_code == 403


def test_unlogged_call_audio_is_purged_after_the_retention_window(db, tmp_path, make_user, monkeypatch):
    from pathlib import Path

    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    dc = make_user(email="dc-retention@example.com", role=Role.DC)
    call = CallSession(
        dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9876543213",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.commit()
    call_svc.submit_voice_note(db, call, audio_bytes=b"fake-audio-bytes", filename="note.m4a", actor=dc)
    db.commit()
    audio_path = Path(call.voice_note.secure_object_ref)
    days = call_svc.settings.unconfirmed_call_audio_retention_days
    now = datetime.now(timezone.utc)

    assert call_svc.purge_stale_call_audio(db, now=now + timedelta(days=days - 1)) == 0
    db.commit()
    assert audio_path.exists()

    assert call_svc.purge_stale_call_audio(db, now=now + timedelta(days=days + 1)) == 1
    db.commit()
    db.refresh(call)
    assert call.voice_note is None
    assert call.recording_status == CallSessionStatus.PURGED
    assert not audio_path.exists()


def test_knowlarity_recording_dropped_for_a_number_not_in_the_crm(db, make_user):
    dc = make_user(email="dc-kw-nocrm@example.com", role=Role.DC)
    call = call_svc.ingest_webhook(db, {
        "call_id": "kw-nocrm-1", "direction": "outgoing", "customer_number": "9811188888",
        "duration": 30, "dc_user_id": dc.id, "recording_url": "https://provider.example/rec/1.mp3",
    })
    db.commit()
    db.refresh(call)
    assert call.recording is None
    assert call.recording_status == CallSessionStatus.NO_RECORDING


# --------------------------------------------------------------------------- calls shorter than 5 seconds


def _call_of_length(client, db, make_user, login, tmp_path, monkeypatch, *, email, phone, seconds):
    from app.models.call_intelligence import CallSession
    from app.services import media_storage

    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    official_id = _crm_territory_with_official(client, make_user, login, dc_email=email, phone=phone)
    call_id = client.post("/api/v1/calls/outgoing", json={"official_id": official_id}).json()["id"]
    db.get(CallSession, call_id).duration_seconds = seconds
    db.commit()
    return call_id


def test_a_recording_of_a_call_under_five_seconds_is_refused_and_nothing_is_stored(
    client, db, make_user, login, tmp_path, monkeypatch
):
    call_id = _call_of_length(client, db, make_user, login, tmp_path, monkeypatch,
                              email="dc-short@example.com", phone="9811100011", seconds=4)
    resp = _upload_call_recording(client, call_id)
    assert resp.status_code == 422 and "5 seconds" in resp.json()["detail"]
    assert list(tmp_path.rglob("*.m4a")) == []
    assert client.get(f"/api/v1/calls/{call_id}").json()["has_voice_note"] is False


def test_a_call_of_exactly_five_seconds_is_still_recorded(client, db, make_user, login, tmp_path, monkeypatch):
    call_id = _call_of_length(client, db, make_user, login, tmp_path, monkeypatch,
                              email="dc-five@example.com", phone="9811100012", seconds=5)
    assert _upload_call_recording(client, call_id).status_code == 200


def test_a_call_with_no_reported_length_is_not_guessed_at(client, db, make_user, login, tmp_path, monkeypatch):
    """0 / unknown means the app did not say how long it was - the recording is let through, not dropped."""
    call_id = _call_of_length(client, db, make_user, login, tmp_path, monkeypatch,
                              email="dc-unk@example.com", phone="9811100013", seconds=0)
    assert _upload_call_recording(client, call_id).status_code == 200


def test_the_dcs_own_voice_note_recap_of_a_short_call_is_still_accepted(
    client, db, make_user, login, tmp_path, monkeypatch
):
    call_id = _call_of_length(client, db, make_user, login, tmp_path, monkeypatch,
                              email="dc-recap@example.com", phone="9811100014", seconds=3)
    resp = client.post(
        f"/api/v1/calls/{call_id}/voice-note",
        files={"file": ("voicenote.m4a", b"fake-audio-bytes", "audio/mp4")},
    )
    assert resp.status_code == 200      # only a recording of the call itself is subject to the minimum
