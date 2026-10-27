"""SBI-official intelligence (the DC-facing briefing), its access boundaries, and the DC-SBI audio flow."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.call_intelligence import CallSession, CallSessionStatus
from app.models.commitment import Commitment, CommitmentSourceKind, CommitmentStatus
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction, Interaction, InteractionType, Sentiment
from app.models.official_date import DateKind, OfficialDate
from app.models.relationship import Relationship
from app.models.task import Task, TaskStatus
from app.models.user import Role
from app.services import call_intelligence as call_svc
from app.services import commitments as commitments_svc
from app.services import media_storage

NOW = datetime.now(timezone.utc)


# --------------------------------------------------------------------------- world: two territories


def _world(client, db, make_user, login):
    """Admin builds two branches (A, B), an official in each, and DC-A / DC-B territories."""
    make_user(email="admin-oi@example.com", role=Role.ADMIN)
    login("admin-oi@example.com", "password123")
    unit = lambda name: client.post("/api/v1/organization/units", json={"name": name, "type_code": "CC"}).json()["id"]  # noqa: E731
    ua, ub = unit("Branch A"), unit("Branch B")
    off = lambda name, u: client.post("/api/v1/officials", json={"name": name, "organization_unit_id": u}).json()["id"]  # noqa: E731
    oa, ob = off("Alice Official", ua), off("Bob Official", ub)
    dc_a = make_user(email="dc-a-oi@example.com", role=Role.DC, name="DC A")
    dc_b = make_user(email="dc-b-oi@example.com", role=Role.DC, name="DC B")
    for dc, u in ((dc_a, ua), (dc_b, ub)):
        assert client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": u}).status_code == 201
    client.post("/api/v1/auth/logout")
    rel_a, rel_b = Relationship(official_id=oa), Relationship(official_id=ob)
    db.add_all([rel_a, rel_b])
    db.commit()
    return {"oa": oa, "ob": ob, "rel_a": rel_a, "rel_b": rel_b, "dc_a": dc_a, "dc_b": dc_b}


def _confirm(db, dc, official_id, rel, brief):
    call = CallSession(dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9000000031",
                       official_id=official_id, relationship_id=rel.id, started_at=NOW)
    db.add(call)
    db.commit()
    call_svc.confirm_and_log(db, call, dc, brief, "link")
    db.commit()
    return call


def _as(client, login, email):
    client.post("/api/v1/auth/logout")
    login(email, "password123")


# --------------------------------------------------------------------------- approval before active


def test_nothing_from_an_unconfirmed_call_becomes_a_commitment(db, make_user, make_official):
    dc = make_user(email="dc-un@example.com", role=Role.DC)
    official = make_official("Un Official")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    call = CallSession(dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9000000032",
                       official_id=official.id, relationship_id=rel.id, started_at=NOW)
    db.add(call)
    db.commit()
    call_svc.set_manual_text(db, call, "Official promised to send the list by 2026-12-05.", dc)
    db.commit()
    assert db.query(Commitment).count() == 0         # a brief exists, but no human has approved it yet


def test_confirming_the_brief_is_the_approval_commitments_become_open_and_tagged(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    _confirm(db, w["dc_a"], w["oa"], w["rel_a"], {"summary": "Renewal.", "commitments": [
        "Official to send the revised list by 2026-12-05.", "DC to share the slab chart.",
        "Official might consider a visit, nothing decided.",
    ]})
    rows = {c.text: c for c in db.query(Commitment).all()}
    assert set(rows) == {"Official to send the revised list by 2026-12-05.", "DC to share the slab chart."}   # hedge dropped
    assert all(c.status == CommitmentStatus.OPEN and c.source_kind == CommitmentSourceKind.DC_OFFICIAL for c in rows.values())
    assert rows["Official to send the revised list by 2026-12-05."].due_date == date(2026, 12, 5)


def test_the_dc_edited_brief_is_what_becomes_active_not_the_original_ai_text(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    _confirm(db, w["dc_a"], w["oa"], w["rel_a"], {"commitments": ["Official to send the corrected list."]})   # edited
    assert [c.text for c in db.query(Commitment).all()] == ["Official to send the corrected list."]


# --------------------------------------------------------------------------- the briefing


def test_briefing_pulls_history_memory_commitments_followups_and_suggestions(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    rel = w["rel_a"]
    # A logged, approved call first (this is what creates the commitments)...
    _confirm(db, w["dc_a"], w["oa"], rel, {"commitments": ["Official to send the revised list.", "DC to call back on the delay."]})
    # ...then the rest of the history: the newest contact was tense, and the thread has gone quiet.
    db.add(Interaction(
        relationship_id=rel.id, official_id=w["oa"], type=InteractionType.CALL, direction=Direction.OUTBOUND,
        occurred_at=NOW + timedelta(minutes=1), raw_notes="Tense call about delays.", ai_summary="Tense call.",
        structured={"highlights": ["Delay on the renewal paperwork"]}, sentiment=Sentiment.NEGATIVE,
    ))
    db.add(Task(relationship_id=rel.id, official_id=w["oa"], title="Send the renewal pack",
                due_at=NOW - timedelta(days=3), status=TaskStatus.OPEN))
    db.add(OfficialDate(official_id=w["oa"], kind=DateKind.BIRTHDAY,
                        value=(NOW + timedelta(days=5)).date().replace(year=1985), source="test"))
    db.refresh(rel)
    rel.last_interaction_at = NOW - timedelta(days=60)
    db.commit()

    _as(client, login, "dc-a-oi@example.com")
    body = client.get(f"/api/v1/officials/{w['oa']}/intelligence").json()

    assert body["official"]["name"] == "Alice Official" and body["relationship"]["id"] == rel.id
    assert body["interactions"][0]["summary"] == "Tense call." and body["interactions"][0]["sentiment"] == "negative"
    assert len(body["interactions"]) == 2                                   # the approved call is in the history too
    assert {"fact": "Delay on the renewal paperwork", "kind": "highlight", "state": None} in body["memory"]
    assert [c["text"] for c in body["commitments"]["theirs"]] == ["Official to send the revised list."]
    assert [c["text"] for c in body["commitments"]["ours"]] == ["DC to call back on the delay."]
    assert body["followups"][0]["title"] == "Send the renewal pack" and body["followups"][0]["overdue"] is True
    assert body["upcoming_dates"] and body["upcoming_dates"][0]["kind"] == "birthday"

    kinds = {i["kind"] for i in body["talking_point_items"]} | {i["kind"] for i in body["followup_suggestion_items"]}
    assert {"close_commitment", "check_theirs", "steady_relationship", "overdue_followup",
            "upcoming_date", "stale_contact"} <= kinds
    assert all(set(i) >= {"key", "type", "kind", "text", "my_verdict"} for i in body["talking_point_items"])


def test_the_briefing_is_just_as_complete_after_the_dc_audio_has_been_discarded(client, db, make_user, login, tmp_path, monkeypatch):
    """The separate DC-SBI retention flow: logging the interaction deletes the audio, transcript and brief
    from the call tables. The official briefing must not depend on any of them."""
    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    w = _world(client, db, make_user, login)
    call = CallSession(dc_user_id=w["dc_a"].id, direction=Direction.OUTBOUND, phone_ref="9000000033",
                       official_id=w["oa"], relationship_id=w["rel_a"].id, started_at=NOW)
    db.add(call)
    db.commit()
    call_svc.submit_voice_note(db, call, audio_bytes=b"audio", filename="n.m4a", actor=w["dc_a"])
    db.commit()
    audio = Path(call.voice_note.secure_object_ref)
    call_svc.set_manual_text(db, call, "Official agreed to send the list.", w["dc_a"])
    db.refresh(call)
    call_svc.confirm_and_log(db, call, w["dc_a"], {"summary": "List agreed.", "commitments": ["Official to send the list."]}, "link")
    db.commit()
    db.refresh(call)

    assert not audio.exists() and call.transcript is None and call.analysis is None and call.voice_note is None
    assert call.recording_status == CallSessionStatus.PURGED
    _as(client, login, "dc-a-oi@example.com")
    body = client.get(f"/api/v1/officials/{w['oa']}/intelligence").json()
    assert [c["text"] for c in body["commitments"]["theirs"]] == ["Official to send the list."]
    assert body["interactions"] and body["interactions"][0]["type"] == "call"      # the logged call is the history


# --------------------------------------------------------------------------- strict DC boundaries


def test_a_dc_reaches_only_officials_in_their_own_territory(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    _as(client, login, "dc-a-oi@example.com")
    assert client.get(f"/api/v1/officials/{w['oa']}/intelligence").status_code == 200
    assert client.get(f"/api/v1/officials/{w['ob']}/intelligence").status_code == 404      # the other DC's official
    _as(client, login, "dc-b-oi@example.com")
    assert client.get(f"/api/v1/officials/{w['ob']}/intelligence").status_code == 200
    assert client.get(f"/api/v1/officials/{w['oa']}/intelligence").status_code == 404


def test_a_dc_without_territory_an_rm_and_anonymous_get_nothing(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    make_user(email="dc-none-oi@example.com", role=Role.DC)
    make_user(email="rm-oi@example.com", role=Role.RELATIONSHIP_MANAGER)
    make_user(email="viewer-oi@example.com", role=Role.APPROVER_VIEWER)
    _as(client, login, "dc-none-oi@example.com")
    assert client.get(f"/api/v1/officials/{w['oa']}/intelligence").status_code == 404
    _as(client, login, "rm-oi@example.com")
    assert client.get(f"/api/v1/officials/{w['oa']}/intelligence").status_code == 404      # RMs have no officials
    _as(client, login, "viewer-oi@example.com")
    assert client.get(f"/api/v1/officials/{w['oa']}/intelligence").status_code == 200      # read-only role may read
    client.post("/api/v1/auth/logout")
    assert client.get(f"/api/v1/officials/{w['oa']}/intelligence").status_code == 401


def _commitment(db, w, official_key="oa", status=CommitmentStatus.OPEN, text="Official to send the list."):
    c = Commitment(official_id=w[official_key], text=text, status=status, party=commitments_svc.CommitmentParty.THEIRS,
                   source_kind=CommitmentSourceKind.DC_OFFICIAL)
    db.add(c)
    db.commit()
    return c


def test_commitment_changes_are_bounded_by_territory_and_role(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    mine, theirs = _commitment(db, w, "oa"), _commitment(db, w, "ob")
    make_user(email="rm-oi2@example.com", role=Role.RELATIONSHIP_MANAGER)
    make_user(email="viewer-oi2@example.com", role=Role.APPROVER_VIEWER)
    _as(client, login, "dc-a-oi@example.com")
    assert client.post(f"/api/v1/officials/commitments/{mine.id}/status", json={"status": "done"}).status_code == 200
    assert client.post(f"/api/v1/officials/commitments/{theirs.id}/status", json={"status": "done"}).status_code == 404
    assert client.get(f"/api/v1/officials/commitments/{theirs.id}/history").status_code == 404
    _as(client, login, "rm-oi2@example.com")
    assert client.post(f"/api/v1/officials/commitments/{mine.id}/status", json={"status": "cancelled"}).status_code == 404
    _as(client, login, "viewer-oi2@example.com")
    assert client.post(f"/api/v1/officials/commitments/{mine.id}/status", json={"status": "cancelled"}).status_code == 403
    db.expire_all()
    assert db.get(Commitment, theirs.id).status == CommitmentStatus.OPEN


def test_a_csp_commitment_is_not_reachable_through_the_official_routes(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    rm = make_user(email="rm-oi3@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = Csp(csp_id="X1", name="C", rm_name="R", rm_user_id=rm.id, mobile="9000000039", status=CspStatus.ACTIVE)
    db.add(csp)
    db.commit()
    c = Commitment(csp_id=csp.id, text="CSP to do X.", status=CommitmentStatus.OPEN,
                   party=commitments_svc.CommitmentParty.THEIRS, source_kind=CommitmentSourceKind.RM_CSP)
    db.add(c)
    db.commit()
    _as(client, login, "dc-a-oi@example.com")
    assert client.post(f"/api/v1/officials/commitments/{c.id}/status", json={"status": "done"}).status_code == 404


def test_official_commitment_duplicates_are_flagged_and_a_dc_rules_on_them(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    _confirm(db, w["dc_a"], w["oa"], w["rel_a"], {"commitments": ["Official to send the revised list by 2026-12-05."]})
    _confirm(db, w["dc_a"], w["oa"], w["rel_a"], {"commitments": ["Official will share the revised list by 2026-12-05."]})
    first, second = db.query(Commitment).order_by(Commitment.id).all()
    assert second.duplicate_review == "flagged" and second.possible_duplicate_of_id == first.id
    assert first.status == second.status == CommitmentStatus.OPEN                       # nothing merged silently
    _as(client, login, "dc-b-oi@example.com")
    assert client.post(f"/api/v1/officials/commitments/{second.id}/duplicate", json={"decision": "merge"}).status_code == 404
    _as(client, login, "dc-a-oi@example.com")
    merged = client.post(f"/api/v1/officials/commitments/{second.id}/duplicate", json={"decision": "merge"})
    assert merged.status_code == 200 and merged.json()["status"] == "cancelled"
    body = client.get(f"/api/v1/officials/{w['oa']}/intelligence").json()
    assert [c["id"] for c in body["commitments"]["theirs"]] == [first.id]
    assert body["commitments"]["theirs"][0]["also_mentioned"][0]["id"] == second.id


# --------------------------------------------------------------------------- feedback


def _items(client, official_id):
    body = client.get(f"/api/v1/officials/{official_id}/intelligence").json()
    return body["talking_point_items"], body["followup_suggestion_items"], body


def test_feedback_is_recorded_validated_and_cannot_be_forged(client, db, make_user, login):
    from app.models.intelligence_feedback import IntelligenceFeedback

    w = _world(client, db, make_user, login)
    _confirm(db, w["dc_a"], w["oa"], w["rel_a"], {"commitments": ["Official to send the list."]})
    db.add(Task(relationship_id=w["rel_a"].id, official_id=w["oa"], title="Chase paperwork",
                due_at=NOW - timedelta(days=2), status=TaskStatus.OPEN))
    db.commit()
    _as(client, login, "dc-a-oi@example.com")
    points, follow, _ = _items(client, w["oa"])
    tp, fu = points[0], follow[0]
    url = f"/api/v1/officials/{w['oa']}/feedback"

    assert client.post(url, json={"target_type": "talking_point", "key": tp["key"], "verdict": "useful"}).status_code == 200
    assert client.post(url, json={"target_type": "followup", "key": fu["key"], "verdict": "relevant"}).status_code == 200
    assert client.post(url, json={"target_type": "talking_point", "key": tp["key"], "verdict": "relevant"}).status_code == 400  # wrong vocabulary
    assert client.post(url, json={"target_type": "banana", "key": tp["key"], "verdict": "useful"}).status_code == 400
    assert client.post(url, json={"target_type": "talking_point", "key": "f" * 16, "verdict": "useful"}).status_code == 404     # forged key
    db.expire_all()
    rows = db.query(IntelligenceFeedback).all()
    assert {(r.target_type, r.kind, r.verdict) for r in rows} == {
        ("talking_point", tp["kind"], "useful"), ("followup", fu["kind"], "relevant")}
    assert all(r.text and r.subject_type == "official" and r.subject_id == w["oa"] for r in rows)   # snapshot is server-side


def test_changing_your_mind_updates_one_row_and_the_page_shows_your_verdict(client, db, make_user, login):
    from app.models.intelligence_feedback import IntelligenceFeedback

    w = _world(client, db, make_user, login)
    _confirm(db, w["dc_a"], w["oa"], w["rel_a"], {"commitments": ["Official to send the list."]})
    _as(client, login, "dc-a-oi@example.com")
    tp = _items(client, w["oa"])[0][0]
    url = f"/api/v1/officials/{w['oa']}/feedback"
    client.post(url, json={"target_type": "talking_point", "key": tp["key"], "verdict": "useful"})
    client.post(url, json={"target_type": "talking_point", "key": tp["key"], "verdict": "not_useful", "note": "already done"})
    assert db.query(IntelligenceFeedback).count() == 1
    assert db.query(IntelligenceFeedback).one().verdict == "not_useful"


def test_feedback_boundaries(client, db, make_user, login):
    w = _world(client, db, make_user, login)
    _confirm(db, w["dc_b"], w["ob"], w["rel_b"], {"commitments": ["Official to send the list."]})
    make_user(email="viewer-fb@example.com", role=Role.APPROVER_VIEWER)
    make_user(email="rm-fb@example.com", role=Role.RELATIONSHIP_MANAGER)
    _as(client, login, "dc-b-oi@example.com")
    key = _items(client, w["ob"])[0][0]["key"]
    body = {"target_type": "talking_point", "key": key, "verdict": "useful"}
    _as(client, login, "dc-a-oi@example.com")
    assert client.post(f"/api/v1/officials/{w['ob']}/feedback", json=body).status_code == 404     # other territory
    _as(client, login, "rm-fb@example.com")
    assert client.post(f"/api/v1/officials/{w['ob']}/feedback", json=body).status_code == 404
    _as(client, login, "viewer-fb@example.com")
    assert client.post(f"/api/v1/officials/{w['ob']}/feedback", json=body).status_code == 403
    client.post("/api/v1/auth/logout")
    assert client.post(f"/api/v1/officials/{w['ob']}/feedback", json=body).status_code == 401


def test_a_not_useful_suggestion_is_hidden_only_for_you_and_only_for_a_while(client, db, make_user, login):
    from app.models.intelligence_feedback import IntelligenceFeedback

    w = _world(client, db, make_user, login)
    _confirm(db, w["dc_a"], w["oa"], w["rel_a"], {"commitments": ["Official to send the list.", "DC to call back."]})
    _as(client, login, "dc-a-oi@example.com")
    points, _, body = _items(client, w["oa"])
    assert len(points) == 2 and body["suppressed_count"] == 0
    gone = points[0]
    client.post(f"/api/v1/officials/{w['oa']}/feedback", json={"target_type": "talking_point", "key": gone["key"], "verdict": "not_useful"})
    points, _, body = _items(client, w["oa"])
    assert gone["key"] not in {p["key"] for p in points} and body["suppressed_count"] == 1    # hidden, and says so
    _as(client, login, "admin-oi@example.com")
    assert gone["key"] in {p["key"] for p in _items(client, w["oa"])[0]}                         # not hidden for others
    row = db.query(IntelligenceFeedback).one()
    row.updated_at = NOW - timedelta(days=31)
    db.commit()
    _as(client, login, "dc-a-oi@example.com")
    assert gone["key"] in {p["key"] for p in _items(client, w["oa"])[0]}                         # reappears after 30 days
