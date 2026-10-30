"""The Android app reads GET /csps/{id}/pre-call and POST /csps/commitments/{id}/status through fixed DTOs
(android/.../dto/PreCallDtos.kt). This pins the response shape so the two cannot drift apart silently,
and checks the phone's access boundary: an RM gets only their own CSP's briefing."""

from datetime import datetime, timezone

from app.models.call_intelligence import CallAIAnalysis, CallSession
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import commitments as svc


def _csp(db, csp_id, rm):
    c = Csp(csp_id=csp_id, name="Agent " + csp_id, rm_name="RM", rm_user_id=rm.id, mobile="9000000011",
            alternate_mobile="9000000012", category="Gold CSP", branch_name="BR", status=CspStatus.ACTIVE)
    db.add(c)
    db.commit()
    return c


def _seed_brief(db, rm, csp):
    call = CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9000000011",
                       started_at=datetime.now(timezone.utc), csp_id=csp.id)
    db.add(call)
    db.flush()
    db.add(CallAIAnalysis(call_session_id=call.id, analysis_json={
        "summary": "Slab 1 not yet achieved.",
        "highlights": ["PMSBY: 26 done", "Slab 1 not yet achieved"],
        "commitments": ["CSP to share the report by 2026-12-01.", "RM to update the system."],
    }))
    db.commit()
    db.refresh(call)
    svc.extract_from_call(db, call)
    db.commit()


def test_precall_response_has_every_field_the_android_dto_reads(client, db, make_user, login):
    rm = make_user(email="rm-contract@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "K1", rm)
    _seed_brief(db, rm, csp)
    login("rm-contract@example.com", "password123")
    body = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()

    for key in ("csp_id", "name", "category", "branch", "rm_name", "mobile", "alternate_mobile", "calls_count",
                "last_call", "open_commitments", "proposed_commitments", "slab_status", "memory", "talking_points"):
        assert key in body, f"missing {key} - Android PreCallDto would break"
    assert set(body["open_commitments"]) >= {"ours", "theirs", "mutual", "total"}
    assert set(body["last_call"]) >= {"call_id", "when", "direction", "summary", "highlights"}
    assert body["memory"] and set(body["memory"][0]) >= {"fact", "kind"}
    prop = body["proposed_commitments"][0]
    assert set(prop) >= {"id", "text", "party", "due_date", "status"} and prop["status"] == "proposed"
    # The score and the TARA panel Android's PreCallDto also reads (TARA is off in this test, so no panel).
    assert set(body["score"]) >= {"version", "overall", "relationship", "business", "band", "tara_included", "reasons"}
    assert "tara" in body and body["tara"] is None


def test_the_tara_panel_has_every_field_the_android_dto_reads(client, db, make_user, login, monkeypatch):
    from app.services import kiosk_kai
    from tests.test_tara_panel import WEAK, WEAK_PROFILE

    rm = make_user(email="rm-contract-tara@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "K3", rm)
    monkeypatch.setattr(kiosk_kai, "configured", lambda: True)
    monkeypatch.setattr(kiosk_kai, "call", lambda tool, **a: WEAK if tool == "tara.csp_performance" else WEAK_PROFILE)
    login("rm-contract-tara@example.com", "password123")

    tara = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()["tara"]

    assert set(tara) >= {"available", "as_of", "month", "slab", "products", "transactions", "earnings", "activity", "caveats"}
    assert set(tara["slab"]) >= {"reached", "reached_in_calling_sheet", "target_in_calling_sheet", "basis", "next"}
    assert set(tara["slab"]["next"]) >= {"name", "incentive_inr", "schemes", "closest_three", "extra_total"}
    assert set(tara["slab"]["next"]["schemes"][0]) >= {"scheme", "have", "threshold", "more"}
    assert set(tara["products"][0]) >= {"code", "name", "achieved", "sbi_target", "tara_goal", "agent_target", "progress", "pace_status"}
    assert set(tara["transactions"]) >= {"count", "gtv_inr", "days_with_data", "last_day_with_data"}
    assert set(tara["earnings"]) >= {"month", "value_inr", "usual_inr", "growth_pct", "status", "rank_in_district", "of_in_district"}
    assert set(tara["activity"]) >= {"days_without_activity", "last_login_date", "terminal_status", "matm_status",
                                     "passbook_printer_status", "gps_dongle_status"}


def test_status_endpoint_returns_the_commitment_shape_android_expects(client, db, make_user, login):
    rm = make_user(email="rm-contract2@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "K2", rm)
    _seed_brief(db, rm, csp)
    login("rm-contract2@example.com", "password123")
    cid = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()["proposed_commitments"][0]["id"]
    accepted = client.post(f"/api/v1/csps/commitments/{cid}/status", json={"status": "open"})
    assert accepted.status_code == 200
    assert set(accepted.json()) >= {"id", "text", "party", "due_date", "status"} and accepted.json()["status"] == "open"


def test_a_phone_cannot_fetch_another_rms_briefing_by_id(client, db, make_user, login):
    rm_a = make_user(email="rm-contract-a@example.com", role=Role.RELATIONSHIP_MANAGER)
    rm_b = make_user(email="rm-contract-b@example.com", role=Role.RELATIONSHIP_MANAGER)
    mine = _csp(db, "KA", rm_a)
    theirs = _csp(db, "KB", rm_b)
    _seed_brief(db, rm_b, theirs)
    login("rm-contract-a@example.com", "password123")
    assert client.get(f"/api/v1/csps/{mine.id}/pre-call").status_code == 200
    assert client.get(f"/api/v1/csps/{theirs.id}/pre-call").status_code == 404


# --------------------------------------------------------------------------- the newer briefing fields


def test_precall_carries_the_suggestion_items_and_duplicate_fields_android_reads(client, db, make_user, login):
    rm = make_user(email="rm-contract3@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "K3", rm)
    _seed_brief(db, rm, csp)
    login("rm-contract3@example.com", "password123")
    body = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()

    for key in ("talking_point_items", "suppressed_count", "performance"):
        assert key in body, f"missing {key} - Android PreCallDto would silently blank it"
    assert body["talking_point_items"] and set(body["talking_point_items"][0]) >= {"key", "type", "kind", "text", "my_verdict"}
    assert "source_call_id" in body["proposed_commitments"][0]   # possible_duplicate / also_mentioned appear only when set (DTO defaults cover absence)

    cid = body["proposed_commitments"][0]["id"]
    done = client.post(f"/api/v1/csps/commitments/{cid}/status", json={"status": "open"})
    closed = client.post(f"/api/v1/csps/commitments/{cid}/status", json={"status": "done", "outcome": "fulfilled"})
    assert done.status_code == closed.status_code == 200 and closed.json()["status"] == "done"

    key = body["talking_point_items"][0]["key"]
    rated = client.post(f"/api/v1/csps/{csp.id}/feedback", json={"target_type": "talking_point", "key": key, "verdict": "useful"})
    assert rated.status_code == 200
    again = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()
    assert {i["key"]: i["my_verdict"] for i in again["talking_point_items"]}.get(key) == "useful"


def test_the_official_briefing_has_every_field_the_android_dto_reads(client, db, make_user, login):
    from datetime import timedelta

    from app.models.interaction import Interaction, InteractionType, Sentiment
    from app.models.official_date import DateKind, OfficialDate
    from app.models.relationship import Relationship
    from app.models.task import Task, TaskStatus

    make_user(email="admin-oc@example.com", role=Role.ADMIN)
    login("admin-oc@example.com", "password123")
    unit = client.post("/api/v1/organization/units", json={"name": "Branch OC", "type_code": "CC"}).json()["id"]
    oid = client.post("/api/v1/officials", json={"name": "Contract Official", "organization_unit_id": unit}).json()["id"]
    dc = make_user(email="dc-oc@example.com", role=Role.DC)
    client.post("/api/v1/dc-territories", json={"dc_user_id": dc.id, "organization_unit_id": unit})
    client.post("/api/v1/auth/logout")

    now = datetime.now(timezone.utc)
    rel = Relationship(official_id=oid, last_interaction_at=now - timedelta(days=40))
    db.add(rel)
    db.commit()
    db.add(Interaction(relationship_id=rel.id, official_id=oid, type=InteractionType.CALL, direction=Direction.OUTBOUND,
                       occurred_at=now, raw_notes="n", ai_summary="Call.", structured={"highlights": ["A fact"]}, sentiment=Sentiment.NEUTRAL))
    db.add(Task(relationship_id=rel.id, official_id=oid, title="Follow up", due_at=now - timedelta(days=1), status=TaskStatus.OPEN))
    db.add(OfficialDate(official_id=oid, kind=DateKind.BIRTHDAY, value=(now + timedelta(days=3)).date().replace(year=1980), source="t"))
    db.commit()

    login("dc-oc@example.com", "password123")
    body = client.get(f"/api/v1/officials/{oid}/intelligence").json()

    for key in ("relationship", "interactions", "memory", "commitments", "proposed_commitments", "followups",
                "upcoming_dates", "talking_point_items", "followup_suggestion_items", "suppressed_count"):
        assert key in body, f"missing {key} - Android OfficialBriefingDto would silently blank it"
    assert {"status", "importance", "score", "band", "days_since_contact"} <= set(body["relationship"])
    assert {"id", "occurred_at", "type", "direction", "sentiment", "summary"} <= set(body["interactions"][0])
    assert {"fact", "kind"} <= set(body["memory"][0])
    assert {"id", "title", "due_at", "overdue"} <= set(body["followups"][0])
    assert {"kind", "label", "in_days"} <= set(body["upcoming_dates"][0])
    assert {"ours", "theirs", "mutual", "total"} <= set(body["commitments"])
    assert body["followup_suggestion_items"] and body["followup_suggestion_items"][0]["type"] == "followup"
