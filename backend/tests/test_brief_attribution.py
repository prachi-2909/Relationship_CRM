"""On an RM-CSP call the RM - not the CSP - tells the CSP how they are performing (where they stand, why,
and what it should be). The brief must record that as the RM's review, and an RM-stated target must not
silently become a CSP commitment."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.call_intelligence import CallAIAnalysis, CallSession
from app.models.commitment import Commitment
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import call_intelligence as ci
from app.services import commitments as svc
from app.services import llm, precall

NOW = datetime.now(timezone.utc)


def _capture(monkeypatch, reply=None):
    seen = []

    def fake(system, user, **_k):
        seen.append(system)
        return reply

    monkeypatch.setattr(llm, "chat", fake)
    return seen


def test_the_rm_csp_prompt_says_the_rm_gives_the_performance_review_and_the_dc_prompt_does_not(monkeypatch):
    seen = _capture(monkeypatch)
    ci.generate_brief(None, SimpleNamespace(csp_id=7), "x")
    ci.generate_brief(None, SimpleNamespace(csp_id=None), "x")
    rm_csp, dc = seen
    assert "WHO SAYS WHAT" in rm_csp and "NOT the CSP" in rm_csp and '"performance"' in rm_csp
    assert "WHERE THEY STAND" in rm_csp and "WHY" in rm_csp and "WHAT IT SHOULD" in rm_csp
    assert "EXPECTATION, not a CSP commitment" in rm_csp
    assert "WHO SAYS WHAT" not in dc and '"performance"' not in dc


def test_a_returned_performance_review_is_kept_and_cleaned(monkeypatch):
    reply = json.dumps({
        "summary": "RM reviewed PMSBY.", "commitments": ["CSP to fix the terminal."],
        "performance": {"what": ["PMSBY: 26 done, Slab 1 not reached"], "why": "terminal expiry blocked it",
                        "should_be": ["Slab 1 needs 30 PMSBY", 5, "", None]},
    })
    _capture(monkeypatch, reply)
    brief = ci.generate_brief(None, SimpleNamespace(csp_id=7), "x")
    assert brief["performance"] == {
        "what": ["PMSBY: 26 done, Slab 1 not reached"],
        "why": ["terminal expiry blocked it"],            # a bare string is wrapped, not dropped
        "should_be": ["Slab 1 needs 30 PMSBY"],            # non-strings and blanks are discarded
    }


def test_garbage_in_performance_never_breaks_the_brief(monkeypatch):
    for bad in ("nonsense", 12, None, ["a"], {"what": {"x": 1}}):
        _capture(monkeypatch, json.dumps({"summary": "ok", "performance": bad}))
        brief = ci.generate_brief(None, SimpleNamespace(csp_id=7), "x")
        assert brief["summary"] == "ok" and brief["performance"] == {"what": [], "why": [], "should_be": []}


def test_a_dc_official_call_never_carries_a_performance_review(monkeypatch):
    _capture(monkeypatch, json.dumps({"summary": "ok", "performance": {"what": ["x"]}}))
    brief = ci.generate_brief(None, SimpleNamespace(csp_id=None), "x")
    assert brief["performance"] == {"what": [], "why": [], "should_be": []}


def test_the_empty_brief_template_cannot_be_polluted_by_a_caller(monkeypatch):
    _capture(monkeypatch, None)
    first = ci.generate_brief(None, SimpleNamespace(csp_id=7), "x")
    first["performance"]["what"].append("leak")
    again = ci.generate_brief(None, SimpleNamespace(csp_id=7), "x")
    assert again["performance"]["what"] == [] and ci._EMPTY_BRIEF["performance"]["what"] == []


def _csp_with_brief(db, make_user, brief, csp_id="PF1", days_ago=0):
    rm = make_user(email=f"{csp_id}@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = Csp(csp_id=csp_id, name="Agent", rm_name="RM", rm_user_id=rm.id, mobile="9000000041", status=CspStatus.ACTIVE)
    db.add(csp)
    db.commit()
    call = CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9000000041",
                       started_at=NOW - timedelta(days=days_ago), csp_id=csp.id)
    db.add(call)
    db.flush()
    db.add(CallAIAnalysis(call_session_id=call.id, analysis_json=brief))
    db.commit()
    db.refresh(call)
    return rm, csp, call


def test_precall_shows_what_the_rm_told_the_csp_and_marks_it_as_the_rms_review(db, make_user):
    brief = {"performance": {"what": ["PMSBY 26 done"], "why": ["terminal expired"], "should_be": ["30 for Slab 1"]}}
    rm, csp, call = _csp_with_brief(db, make_user, brief)
    perf = precall.build_for_csp(db, csp, rm)["performance"]
    assert perf["what"] == ["PMSBY 26 done"] and perf["why"] == ["terminal expired"]
    assert perf["should_be"] == ["30 for Slab 1"] and perf["from"]


def test_precall_has_no_performance_block_when_no_brief_recorded_one(db, make_user):
    rm, csp, call = _csp_with_brief(db, make_user, {"summary": "short call"}, "PF2")
    assert precall.build_for_csp(db, csp, rm)["performance"] is None


def test_an_old_performance_review_ages_out_of_the_briefing(db, make_user):
    brief = {"performance": {"what": ["old numbers"], "why": [], "should_be": []}}
    rm, csp, call = _csp_with_brief(db, make_user, brief, "PF3", days_ago=500)
    assert precall.build_for_csp(db, csp, rm)["performance"] is None


def test_a_target_the_rm_states_is_not_turned_into_a_csp_commitment(db, make_user):
    brief = {
        "performance": {"what": ["26 done"], "why": ["terminal"], "should_be": ["CSP to reach 30 PMSBY this month"]},
        "commitments": ["CSP to fix the terminal."],            # the CSP actually promised this
    }
    rm, csp, call = _csp_with_brief(db, make_user, brief, "PF4")
    svc.extract_from_call(db, call)
    db.commit()
    assert [c.text for c in db.query(Commitment).all()] == ["CSP to fix the terminal."]
