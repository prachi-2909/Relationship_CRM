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
