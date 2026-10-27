"""The AI only PROPOSES commitments: nothing is an obligation until a human accepts it (RM-CSP) or
approves the brief (DC-official), hedged wording is never extracted, and reading a page never writes."""

from datetime import date, datetime, timezone

from app.models.call_intelligence import CallAIAnalysis, CallSession
from app.models.commitment import Commitment, CommitmentSourceKind, CommitmentStatus
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import commitments as svc


def _csp(db, csp_id, rm_user_id):
    c = Csp(csp_id=csp_id, name="Agent", rm_name="RM", rm_user_id=rm_user_id, mobile="9000000002",
            category="Gold CSP", status=CspStatus.ACTIVE)
    db.add(c)
    db.commit()
    return c


def _call(db, dc_user_id, brief, csp=None):
    call = CallSession(dc_user_id=dc_user_id, direction=Direction.OUTBOUND, phone_ref="9000000002",
                       started_at=datetime.now(timezone.utc), csp_id=csp.id if csp else None)
    db.add(call)
    db.flush()
    db.add(CallAIAnalysis(call_session_id=call.id, analysis_json=brief))
    db.commit()
    db.refresh(call)
    return call


def test_hedged_or_merely_discussed_lines_are_not_extracted(db, make_user):
    rm = make_user(email="h1@example.com")
    csp = _csp(db, "H1", rm.id)
    call = _call(db, rm.id, csp=csp, brief={"commitments": [
        "CSP might consider sending the report, nothing decided.",
        "We discussed possibly arranging a visit.",
        "CSP will try to fix the terminal if time permits.",
        "CSP to share the report by 2026-12-01.",  # a real, agreed commitment
    ]})
    out = svc.extract_from_call(db, call)
    assert [c.text for c in out] == ["CSP to share the report by 2026-12-01."]


def test_extraction_from_an_unapproved_brief_is_only_a_proposal(db, make_user):
    rm = make_user(email="h2@example.com")
    csp = _csp(db, "H2", rm.id)
    call = _call(db, rm.id, csp=csp, brief={"commitments": ["CSP to fix the terminal."]})
    svc.extract_from_call(db, call)
    assert db.query(Commitment).one().status == CommitmentStatus.PROPOSED


def test_proposals_are_not_obligations_until_accepted(client, db, make_user, login):
    rm = make_user(email="h3@example.com")
    csp = _csp(db, "H3", rm.id)
    call = _call(db, rm.id, csp=csp, brief={"commitments": ["RM to send the slab chart."]})
    svc.extract_from_call(db, call)
    db.commit()
    login("h3@example.com", "password123")
    pre = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()
    assert pre["open_commitments"]["total"] == 0
    assert [p["text"] for p in pre["proposed_commitments"]] == ["RM to send the slab chart."]
    assert not any("slab chart" in t for t in pre["talking_points"])  # not yet an obligation
    cid = pre["proposed_commitments"][0]["id"]
    client.post(f"/api/v1/csps/commitments/{cid}/status", json={"status": "open"})
    pre = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()
    assert pre["open_commitments"]["total"] == 1 and pre["proposed_commitments"] == []
    assert any("slab chart" in t for t in pre["talking_points"])


def test_dismissed_proposal_stays_dismissed_when_the_brief_is_reprocessed(client, db, make_user, login):
    rm = make_user(email="h4@example.com")
    csp = _csp(db, "H4", rm.id)
    call = _call(db, rm.id, csp=csp, brief={"commitments": ["CSP to do Z."]})
    svc.extract_from_call(db, call)
    db.commit()
    cid = db.query(Commitment).one().id
    login("h4@example.com", "password123")
    client.post(f"/api/v1/csps/commitments/{cid}/status", json={"status": "cancelled"})
    svc.extract_from_call(db, call)
    db.commit()
    assert db.query(Commitment).count() == 1
    assert db.query(Commitment).one().status == CommitmentStatus.CANCELLED


def test_reading_pages_never_writes_commitments(client, db, make_user, login):
    rm = make_user(email="h5@example.com")
    csp = _csp(db, "H5", rm.id)
    _call(db, rm.id, csp=csp, brief={"commitments": ["CSP to do Q."]})  # a brief exists, nothing extracted
    login("h5@example.com", "password123")
    for path in ("pre-call", "commitments", "profile"):
        assert client.get(f"/api/v1/csps/{csp.id}/{path}").status_code == 200
    db.expire_all()
    assert db.query(Commitment).count() == 0


def test_a_new_brief_refreshes_stale_proposals_but_keeps_accepted_ones(db, make_user):
    rm = make_user(email="h6@example.com")
    csp = _csp(db, "H6", rm.id)
    call = _call(db, rm.id, csp=csp, brief={"commitments": ["CSP to do A.", "CSP to do B."]})
    svc.extract_from_call(db, call)
    db.commit()
    a = db.query(Commitment).filter(Commitment.text == "CSP to do A.").one()
    svc.set_status(db, a, CommitmentStatus.OPEN, rm)
    call.analysis.analysis_json = {"commitments": ["CSP to do A.", "CSP to do C."]}  # re-recorded brief
    db.commit()
    svc.extract_from_call(db, call)
    db.commit()
    got = {c.text: c.status for c in db.query(Commitment).all()}
    assert got == {
        "CSP to do A.": CommitmentStatus.OPEN,        # accepted one untouched and not duplicated
        "CSP to do C.": CommitmentStatus.PROPOSED,    # new proposal; stale proposal B is gone
    }


def test_pipeline_hook_proposes_for_csp_calls_only(db, make_user, make_official):
    rm = make_user(email="h7@example.com")
    csp = _csp(db, "H7", rm.id)
    off = make_official("Off")
    csp_call = _call(db, rm.id, csp=csp, brief={"commitments": ["CSP to do X."]})
    dc_call = _call(db, rm.id, brief={"commitments": ["Official to do Y."]})
    dc_call.official_id = off.id
    db.commit()
    svc.propose_for_new_brief(db, csp_call)
    svc.propose_for_new_brief(db, dc_call)
    db.commit()
    assert [c.text for c in db.query(Commitment).all()] == ["CSP to do X."]


def test_dc_confirm_makes_commitments_open_from_the_approved_edited_brief(db, make_user, make_official):
    dc = make_user(email="dcx@example.com", role=Role.DC)
    off = make_official("Off2")
    call = _call(db, dc.id, brief={"commitments": ["Official to do OLD."]})
    call.official_id = off.id
    db.commit()
    edited = {"commitments": ["Official to send the list by 2026-12-05."]}  # what the DC approved
    svc.extract_from_call(db, call, brief=edited, status=CommitmentStatus.OPEN)
    db.commit()
    rows = db.query(Commitment).all()
    assert [(c.text, c.status, c.source_kind) for c in rows] == [
        ("Official to send the list by 2026-12-05.", CommitmentStatus.OPEN, CommitmentSourceKind.DC_OFFICIAL)
    ]
    assert rows[0].due_date == date(2026, 12, 5)


def test_nothing_marks_a_commitment_done_automatically(db, make_user):
    rm = make_user(email="h8@example.com")
    csp = _csp(db, "H8", rm.id)
    c1 = _call(db, rm.id, csp=csp, brief={"commitments": ["CSP to fix the terminal."]})
    svc.extract_from_call(db, c1)
    db.commit()
    c = db.query(Commitment).one()
    svc.set_status(db, c, CommitmentStatus.OPEN, rm)
    # a later call even mentions the same thing - that must not close the commitment
    c2 = _call(db, rm.id, csp=csp, brief={"summary": "Terminal fixed? CSP says yes.", "commitments": []})
    svc.extract_from_call(db, c2)
    db.commit()
    db.refresh(c)
    assert c.status == CommitmentStatus.OPEN and c.done_at is None
