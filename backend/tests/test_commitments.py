"""Commitment tracking: extraction accuracy, idempotency, and (negative) access control.

Extraction runs on the structured brief a call already has; these tests pin down how it behaves on
awkward real-world wording (ambiguous owner, no deadline, bad dates, duplicates, repeated runs) and
that an RM can never reach another RM's CSP data by changing an id.
"""

from datetime import date, datetime, timezone

import pytest

from app.models.audit import AuditLog
from app.models.call_intelligence import CallAIAnalysis, CallSession
from app.models.commitment import Commitment, CommitmentParty, CommitmentSourceKind, CommitmentStatus
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import commitments as svc


def _csp(db, *, csp_id, rm_user_id, name="Agent"):
    c = Csp(
        csp_id=csp_id, name=name, rm_name="RM", rm_user_id=rm_user_id, mobile="9000000001",
        category="Gold CSP", status=CspStatus.ACTIVE,
    )
    db.add(c)
    db.commit()
    return c


def _call_with_brief(db, *, dc_user_id, csp=None, brief=None):
    call = CallSession(
        dc_user_id=dc_user_id, direction=Direction.OUTBOUND, phone_ref="9000000001",
        started_at=datetime.now(timezone.utc), csp_id=csp.id if csp else None,
    )
    db.add(call)
    db.flush()
    db.add(CallAIAnalysis(call_session_id=call.id, analysis_json=brief or {}))
    db.commit()
    db.refresh(call)
    return call


# --------------------------------------------------------------------------- extraction accuracy


def test_ownership_comes_from_the_subject_of_the_sentence(db, make_user):
    rm = make_user(email="rm1@example.com")
    csp = _csp(db, csp_id="A1", rm_user_id=rm.id)
    call = _call_with_brief(db, dc_user_id=rm.id, csp=csp, brief={
        "commitments": [
            "CSP to fix the terminal expiry issue.",
            "RM to update the system with the new figures.",
            "Both sides agreed to review progress next week.",
        ],
    })
    svc.extract_from_call(db, call)
    db.commit()
    by_text = {c.text: c.party for c in db.query(Commitment).all()}
    assert by_text["CSP to fix the terminal expiry issue."] == CommitmentParty.THEIRS
    assert by_text["RM to update the system with the new figures."] == CommitmentParty.OURS
    assert by_text["Both sides agreed to review progress next week."] == CommitmentParty.MUTUAL


def test_missing_deadline_stays_null_not_guessed(db, make_user):
    rm = make_user(email="rm2@example.com")
    csp = _csp(db, csp_id="A2", rm_user_id=rm.id)
    call = _call_with_brief(db, dc_user_id=rm.id, csp=csp, brief={"commitments": ["CSP to share the report."]})
    svc.extract_from_call(db, call)
    db.commit()
    assert db.query(Commitment).one().due_date is None


@pytest.mark.parametrize("text,expected", [
    ("CSP to finish by 2026-11-10", date(2026, 11, 10)),
    ("CSP to finish by 99th", None),            # not a day of month
    ("CSP to finish by 2026-13-45", None),      # impossible ISO date
    ("CSP to finish by 31st", "31st"),          # resolved to a real date in the next 31 days or None
])
def test_due_date_parsing_never_invents_an_impossible_date(text, expected):
    today = date(2026, 11, 20)
    got = svc._due_date(text, today)
    if expected == "31st":
        # Nov has 30 days: must not crash and must not return an invalid date.
        assert got is None or (got >= today and got.day == 31)
    else:
        assert got == expected


def test_a_past_day_of_month_rolls_to_next_month_not_the_past():
    got = svc._due_date("send by 5th", date(2026, 11, 20))
    assert got == date(2026, 12, 5)


def test_extraction_is_idempotent_and_dedupes_within_a_brief(db, make_user):
    rm = make_user(email="rm3@example.com")
    csp = _csp(db, csp_id="A3", rm_user_id=rm.id)
    call = _call_with_brief(db, dc_user_id=rm.id, csp=csp, brief={
        "commitments": ["CSP to fix the terminal.", "csp to fix the terminal."],
        "action_items": ["CSP to fix the terminal."],
    })
    svc.extract_from_call(db, call)
    db.commit()
    svc.extract_from_call(db, call)  # a second run must not duplicate
    db.commit()
    assert db.query(Commitment).count() == 1


def test_done_commitment_is_not_resurrected_by_a_later_sync(db, make_user):
    rm = make_user(email="rm4@example.com")
    csp = _csp(db, csp_id="A4", rm_user_id=rm.id)
    call = _call_with_brief(db, dc_user_id=rm.id, csp=csp, brief={"commitments": ["CSP to fix the terminal."]})
    svc.extract_from_call(db, call)
    db.commit()
    c = db.query(Commitment).one()
    svc.set_status(db, c, CommitmentStatus.OPEN, rm)   # accept
    svc.set_status(db, c, CommitmentStatus.DONE, rm)
    svc.extract_from_call(db, call)  # re-derive from the same brief
    db.commit()
    db.refresh(c)
    assert c.status == CommitmentStatus.DONE
    assert db.query(Commitment).count() == 1


def test_free_text_outside_commitment_fields_is_never_turned_into_a_commitment(db, make_user):
    rm = make_user(email="rm5@example.com")
    csp = _csp(db, csp_id="A5", rm_user_id=rm.id)
    call = _call_with_brief(db, dc_user_id=rm.id, csp=csp, brief={
        "summary": "CSP will probably send the report by 10th.",
        "key_points": ["We discussed the terminal."],
        "highlights": ["Slab 1 not yet achieved"],
    })
    assert svc.extract_from_call(db, call) == []


def test_source_kind_separates_the_two_streams(db, make_user, make_official):
    rm = make_user(email="rm6@example.com")
    dc = make_user(email="dc6@example.com", role=Role.DC)
    csp = _csp(db, csp_id="A6", rm_user_id=rm.id)
    off = make_official("Some Official")
    rm_call = _call_with_brief(db, dc_user_id=rm.id, csp=csp, brief={"commitments": ["CSP to do X."]})
    dc_call = _call_with_brief(db, dc_user_id=dc.id, brief={"commitments": ["Official to do Y."]})
    dc_call.official_id = off.id
    db.commit()
    svc.extract_from_call(db, rm_call)
    svc.extract_from_call(db, dc_call)
    db.commit()
    kinds = {c.text: c.source_kind for c in db.query(Commitment).all()}
    assert kinds["CSP to do X."] == CommitmentSourceKind.RM_CSP
    assert kinds["Official to do Y."] == CommitmentSourceKind.DC_OFFICIAL


def test_extraction_and_status_changes_are_audited(db, make_user):
    rm = make_user(email="rm7@example.com")
    csp = _csp(db, csp_id="A7", rm_user_id=rm.id)
    call = _call_with_brief(db, dc_user_id=rm.id, csp=csp, brief={"commitments": ["CSP to do X."]})
    svc.extract_from_call(db, call)
    db.commit()
    c = db.query(Commitment).one()
    svc.set_status(db, c, CommitmentStatus.OPEN, rm)
    svc.set_status(db, c, CommitmentStatus.DONE, rm)
    actions = {a.action for a in db.query(AuditLog).all()}
    assert {"commitment.proposed", "commitment.accepted", "commitment.done"} <= actions


# --------------------------------------------------------------------------- access control (negative)


def _two_rms_with_csps(db, make_user):
    rm_a = make_user(email="rm-a@example.com", name="A")
    rm_b = make_user(email="rm-b@example.com", name="B")
    csp_a = _csp(db, csp_id="CA", rm_user_id=rm_a.id, name="A's CSP")
    csp_b = _csp(db, csp_id="CB", rm_user_id=rm_b.id, name="B's CSP")
    call_b = _call_with_brief(db, dc_user_id=rm_b.id, csp=csp_b, brief={"commitments": ["CSP to do B things."]})
    svc.extract_from_call(db, call_b)
    db.commit()
    return rm_a, rm_b, csp_a, csp_b


def test_rm_cannot_read_another_rms_csp_by_changing_the_id(client, db, make_user, login):
    _, _, csp_a, csp_b = _two_rms_with_csps(db, make_user)
    login("rm-a@example.com", "password123")
    assert client.get(f"/api/v1/csps/{csp_a.id}/pre-call").status_code == 200  # own CSP works
    for path in ("pre-call", "commitments", "profile"):
        r = client.get(f"/api/v1/csps/{csp_b.id}/{path}")
        assert r.status_code == 404, f"{path} leaked another RM's CSP: {r.status_code}"


def test_rm_cannot_add_or_change_commitments_on_another_rms_csp(client, db, make_user, login):
    _, _, csp_a, csp_b = _two_rms_with_csps(db, make_user)
    victim = db.query(Commitment).filter(Commitment.csp_id == csp_b.id).one()
    login("rm-a@example.com", "password123")
    add = client.post(f"/api/v1/csps/{csp_b.id}/commitments", json={"text": "injected"})
    assert add.status_code == 404
    upd = client.post(f"/api/v1/csps/commitments/{victim.id}/status", json={"status": "done"})
    assert upd.status_code == 404
    db.expire_all()
    assert db.get(Commitment, victim.id).status == CommitmentStatus.PROPOSED  # untouched


def test_dc_cannot_use_csp_commitment_endpoints(client, db, make_user, login):
    _, _, csp_a, _ = _two_rms_with_csps(db, make_user)
    make_user(email="dc-x@example.com", role=Role.DC)
    login("dc-x@example.com", "password123")
    assert client.get(f"/api/v1/csps/{csp_a.id}/pre-call").status_code == 403
    assert client.get(f"/api/v1/csps/{csp_a.id}/commitments").status_code == 403


def test_unauthenticated_requests_are_rejected(client, db, make_user):
    _, _, csp_a, _ = _two_rms_with_csps(db, make_user)
    assert client.get(f"/api/v1/csps/{csp_a.id}/pre-call").status_code == 401
    assert client.post("/api/v1/csps/commitments/1/status", json={"status": "done"}).status_code == 401


def test_invalid_status_is_rejected(client, db, make_user, login):
    rm_a, _, csp_a, _ = _two_rms_with_csps(db, make_user)
    call = _call_with_brief(db, dc_user_id=rm_a.id, csp=csp_a, brief={"commitments": ["CSP to do A."]})
    svc.extract_from_call(db, call)
    db.commit()
    c = db.query(Commitment).filter(Commitment.csp_id == csp_a.id).one()
    login("rm-a@example.com", "password123")
    url = f"/api/v1/csps/commitments/{c.id}/status"
    assert client.post(url, json={"status": "banana"}).status_code == 400
    assert client.post(url, json={"status": "proposed"}).status_code == 400   # cannot go back
    assert client.post(url, json={"status": "done"}).status_code == 400       # must accept first
    assert client.post(url, json={"status": "open"}).json()["status"] == "open"  # accept
    ok = client.post(url, json={"status": "done"})
    assert ok.status_code == 200 and ok.json()["status"] == "done"


def test_empty_state_for_a_csp_with_no_calls(client, db, make_user, login):
    rm = make_user(email="rm-empty@example.com")
    csp = _csp(db, csp_id="E1", rm_user_id=rm.id)
    login("rm-empty@example.com", "password123")
    body = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()
    assert body["open_commitments"]["total"] == 0
    assert body["talking_points"] == [] and body["last_call"] is None and body["memory"] == []
