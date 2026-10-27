"""Outcome feedback and the quality metrics built from it.

The point of these tests is the *discipline*: only explicit human decisions count as evidence, a rate is
withheld until there are enough of them, and what people rate changes what they see only in two small,
transparent ways."""

from datetime import datetime, timedelta, timezone

from app.models.call_intelligence import CallAIAnalysis, CallSession
from app.models.commitment import Commitment, CommitmentEvent, CommitmentSourceKind, CommitmentStatus
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.intelligence_feedback import IntelligenceFeedback
from app.models.relationship import Relationship
from app.models.user import Role
from app.services import call_intelligence as call_svc
from app.services import commitments as svc
from app.services import intelligence_feedback as fb

NOW = datetime.now(timezone.utc)


def _rm_csp(db, make_user, tag, brief=None):
    rm = make_user(email=f"{tag}@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = Csp(csp_id=tag.upper(), name="Agent " + tag, rm_name="RM", rm_user_id=rm.id, mobile="9000000051",
              status=CspStatus.ACTIVE)
    db.add(csp)
    db.commit()
    if brief is not None:
        call = CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9000000051",
                           started_at=NOW, csp_id=csp.id)
        db.add(call)
        db.flush()
        db.add(CallAIAnalysis(call_session_id=call.id, analysis_json=brief))
        db.commit()
        db.refresh(call)
        svc.extract_from_call(db, call)
        db.commit()
        for c in db.query(Commitment).filter(Commitment.csp_id == csp.id).all():
            svc.set_status(db, c, CommitmentStatus.OPEN, rm)       # accept, so they become talking points
    return rm, csp


def _precall(client, csp):
    return client.get(f"/api/v1/csps/{csp.id}/pre-call").json()


# --------------------------------------------------------------------------- CSP feedback


def test_an_rm_rates_a_talking_point_and_sees_their_own_verdict(client, db, make_user, login):
    rm, csp = _rm_csp(db, make_user, "fb1", {"commitments": ["CSP to fix the terminal.", "RM to send the slab chart."]})
    login("fb1@example.com", "password123")
    body = _precall(client, csp)
    items = body["talking_point_items"]
    assert {i["kind"] for i in items} == {"check_theirs", "close_commitment"}
    assert body["talking_points"] == [i["text"] for i in items]                    # older clients keep working
    url = f"/api/v1/csps/{csp.id}/feedback"
    assert client.post(url, json={"target_type": "talking_point", "key": items[0]["key"], "verdict": "useful"}).status_code == 200
    mine = {i["key"]: i["my_verdict"] for i in _precall(client, csp)["talking_point_items"]}
    assert mine[items[0]["key"]] == "useful" and mine[items[1]["key"]] is None
    row = db.query(IntelligenceFeedback).one()
    assert (row.subject_type, row.subject_id, row.kind, row.verdict) == ("csp", csp.id, items[0]["kind"], "useful")


def test_csp_feedback_is_validated_scoped_and_unforgeable(client, db, make_user, login):
    rm, csp = _rm_csp(db, make_user, "fb2", {"commitments": ["CSP to fix the terminal."]})
    other_rm, other_csp = _rm_csp(db, make_user, "fb2b", {"commitments": ["CSP to fix the printer."]})
    make_user(email="dc-fb2@example.com", role=Role.DC)
    login("fb2@example.com", "password123")
    key = _precall(client, csp)["talking_point_items"][0]["key"]
    url = f"/api/v1/csps/{csp.id}/feedback"
    ok = {"target_type": "talking_point", "key": key, "verdict": "useful"}
    assert client.post(url, json={**ok, "verdict": "relevant"}).status_code == 400            # wrong vocabulary
    assert client.post(url, json={**ok, "target_type": "banana"}).status_code == 400
    assert client.post(url, json={**ok, "key": "0" * 16}).status_code == 404                  # forged key
    assert client.post(f"/api/v1/csps/{other_csp.id}/feedback", json=ok).status_code == 404   # another RM's CSP
    client.post("/api/v1/auth/logout")
    login("dc-fb2@example.com", "password123")
    assert client.post(url, json=ok).status_code == 403
    client.post("/api/v1/auth/logout")
    assert client.post(url, json=ok).status_code == 401
    assert db.query(IntelligenceFeedback).count() == 0                                         # nothing slipped in


def test_a_not_useful_talking_point_is_hidden_for_that_rm_only_and_counted(client, db, make_user, login):
    rm, csp = _rm_csp(db, make_user, "fb3", {"commitments": ["CSP to fix the terminal.", "RM to send the slab chart."]})
    make_user(email="admin-fb3@example.com", role=Role.ADMIN)
    login("fb3@example.com", "password123")
    items = _precall(client, csp)["talking_point_items"]
    gone = items[0]
    client.post(f"/api/v1/csps/{csp.id}/feedback", json={"target_type": "talking_point", "key": gone["key"], "verdict": "not_useful"})
    body = _precall(client, csp)
    assert gone["key"] not in {i["key"] for i in body["talking_point_items"]} and body["suppressed_count"] == 1
    client.post("/api/v1/auth/logout")
    login("admin-fb3@example.com", "password123")
    assert gone["key"] in {i["key"] for i in _precall(client, csp)["talking_point_items"]}     # others still see it


# --------------------------------------------------------------------------- reordering is gated and transparent


def _rate(db, user_id, kind, verdict, n, tag, subject=1):
    for i in range(n):
        db.add(IntelligenceFeedback(user_id=user_id * 1000 + i, subject_type="csp", subject_id=subject,
                                    target_type="talking_point", target_key=f"{tag}{i}", kind=kind,
                                    text="t", verdict=verdict))
    db.commit()


def test_nothing_is_reordered_until_a_kind_has_enough_ratings(db):
    items = [fb.make_item("talking_point", "a_kind", "A"), fb.make_item("talking_point", "b_kind", "B")]
    _rate(db, 1, "a_kind", "not_useful", fb.MIN_SAMPLE - 1, "a")        # one short of enough
    _rate(db, 2, "b_kind", "useful", fb.MIN_SAMPLE - 1, "b")
    out, hidden = fb.apply_feedback(db, None, "csp", 99, items)
    assert [i["kind"] for i in out] == ["a_kind", "b_kind"] and hidden == 0


def test_a_kind_people_find_more_useful_is_listed_first_but_nothing_is_removed(db):
    items = [fb.make_item("talking_point", "a_kind", "A"), fb.make_item("talking_point", "b_kind", "B"),
             fb.make_item("talking_point", "c_kind", "C")]
    _rate(db, 1, "a_kind", "not_useful", fb.MIN_SAMPLE, "a")
    _rate(db, 2, "b_kind", "useful", fb.MIN_SAMPLE, "b")
    out, hidden = fb.apply_feedback(db, None, "csp", 99, items)
    assert [i["kind"] for i in out] == ["b_kind", "c_kind", "a_kind"]   # liked, unrated (neutral), disliked
    assert len(out) == 3 and hidden == 0                                 # all still there for everyone


# --------------------------------------------------------------------------- quality metrics


def _ev(db, c, action, actor_id, **detail):
    db.add(CommitmentEvent(commitment_id=c.id, action=action, actor_id=actor_id, detail=detail or None))


def _bare_commitment(db):
    c = Commitment(csp_id=None, official_id=None, text="x", status=CommitmentStatus.OPEN,
                   source_kind=CommitmentSourceKind.RM_CSP)
    db.add(c)
    db.flush()
    return c


def test_rates_are_withheld_below_the_minimum_sample_then_reported(db, make_user):
    rm = make_user(email="q1@example.com", role=Role.RELATIONSHIP_MANAGER)
    c = _bare_commitment(db)
    for _ in range(fb.MIN_SAMPLE - 1):
        _ev(db, c, "accepted", rm.id)
    db.commit()
    m = fb.quality_metrics(db)["proposals"]
    assert m["n"] == fb.MIN_SAMPLE - 1 and m["rate"] is None and m["enough_data"] is False   # honest: not enough
    _ev(db, c, "dismissed", rm.id)
    db.commit()
    m = fb.quality_metrics(db)["proposals"]
    assert m["accepted"] == fb.MIN_SAMPLE - 1 and m["dismissed"] == 1
    assert m["enough_data"] is True and m["rate"] == round((fb.MIN_SAMPLE - 1) / fb.MIN_SAMPLE, 3)


def test_only_explicit_human_actions_count_never_system_events_or_approvals(db, make_user):
    rm = make_user(email="q2@example.com", role=Role.RELATIONSHIP_MANAGER)
    c = _bare_commitment(db)
    for _ in range(12):
        _ev(db, c, "expired", None)                       # the system expiring a proposal is NOT a dismissal
        _ev(db, c, "proposed", None)
        _ev(db, c, "approved_with_brief", rm.id)          # approving a whole brief is NOT accepting this item
        _ev(db, c, "possible_duplicate", None)
        # even an event that LOOKS like a human decision does not count when no person made it
        for action in ("accepted", "dismissed", "done", "cancelled", "merged", "kept_separate"):
            _ev(db, c, action, None)
    db.commit()
    m = fb.quality_metrics(db)
    assert m["proposals"]["n"] == 0 and m["fulfilment"]["n"] == 0 and m["duplicate_flags"]["n"] == 0


def test_a_call_a_confirmed_brief_or_an_extraction_never_adds_evidence(db, make_user, make_official):
    dc = make_user(email="q3@example.com", role=Role.DC)
    official = make_official("Q Official")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    call = CallSession(dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref="9000000052",
                       official_id=official.id, relationship_id=rel.id, started_at=NOW)
    db.add(call)
    db.commit()
    call_svc.confirm_and_log(db, call, dc, {"commitments": ["Official to send the list."]}, "link")
    db.commit()
    m = fb.quality_metrics(db)
    assert db.query(Commitment).count() == 1                       # the commitment exists...
    assert m["proposals"]["n"] == 0 and m["fulfilment"]["n"] == 0 and m["talking_points"]["overall"]["n"] == 0


def test_fulfilment_duplicate_precision_and_per_kind_usefulness_are_measured(db, make_user):
    rm = make_user(email="q4@example.com", role=Role.RELATIONSHIP_MANAGER)
    c = _bare_commitment(db)
    for _ in range(8):
        _ev(db, c, "done", rm.id, outcome="fulfilled")
    for _ in range(2):
        _ev(db, c, "cancelled", rm.id, outcome="not_fulfilled")
    for _ in range(9):
        _ev(db, c, "merged", rm.id)
    _ev(db, c, "kept_separate", rm.id)
    db.commit()
    _rate(db, 3, "check_theirs", "useful", 7, "u")
    _rate(db, 4, "check_theirs", "not_useful", 3, "n")
    m = fb.quality_metrics(db)
    assert m["fulfilment"]["done"] == 8 and m["fulfilment"]["closed_without_doing"] == 2
    assert m["fulfilment"]["reported_not_fulfilled"] == 2 and m["fulfilment"]["rate"] == 0.8
    assert m["duplicate_flags"]["confirmed_duplicate"] == 9 and m["duplicate_flags"]["rate"] == 0.9
    kind = m["talking_points"]["by_kind"]["check_theirs"]
    assert kind["n"] == 10 and kind["positive"] == 7 and kind["rate"] == 0.7


def test_the_quality_endpoint_is_for_admin_and_viewer_only(client, db, make_user, login):
    for tag, role in (("adm", Role.ADMIN), ("view", Role.APPROVER_VIEWER), ("rmq", Role.RELATIONSHIP_MANAGER), ("dcq", Role.DC)):
        make_user(email=f"{tag}-q@example.com", role=role)
    for tag, expected in (("adm", 200), ("view", 200), ("rmq", 403), ("dcq", 403)):
        client.post("/api/v1/auth/logout")
        login(f"{tag}-q@example.com", "password123")
        assert client.get("/api/v1/intelligence/quality").status_code == expected, tag
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/intelligence/quality").status_code == 401
    body = client.get("/api/v1/intelligence/quality")
    assert body.status_code == 401


def test_end_to_end_decisions_made_in_the_app_show_up_in_the_metrics(client, db, make_user, login):
    rm, csp = _rm_csp(db, make_user, "q5")
    make_user(email="adm5@example.com", role=Role.ADMIN)
    call = CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9000000051",
                       started_at=NOW, csp_id=csp.id)
    db.add(call)
    db.flush()
    db.add(CallAIAnalysis(call_session_id=call.id, analysis_json={"commitments": ["CSP to fix the terminal.", "CSP to send the report."]}))
    db.commit()
    db.refresh(call)
    svc.extract_from_call(db, call)
    db.commit()
    a, b = db.query(Commitment).order_by(Commitment.id).all()
    login("q5@example.com", "password123")
    assert client.post(f"/api/v1/csps/commitments/{a.id}/status", json={"status": "open"}).status_code == 200
    assert client.post(f"/api/v1/csps/commitments/{b.id}/status", json={"status": "cancelled"}).status_code == 200   # dismiss
    client.post("/api/v1/auth/logout")
    login("adm5@example.com", "password123")
    m = client.get("/api/v1/intelligence/quality").json()
    assert (m["proposals"]["accepted"], m["proposals"]["dismissed"]) == (1, 1)
    assert m["proposals"]["rate"] is None and m["min_sample"] == fb.MIN_SAMPLE


# --------------------------------------------------------------------------- retention


def test_old_feedback_is_purged_recent_feedback_stays_and_the_audit_has_no_text(db):
    from app.models.audit import AuditLog
    from app.services import retention

    _rate(db, 5, "check_theirs", "useful", 3, "keep")
    for i in range(2):
        db.add(IntelligenceFeedback(user_id=9000 + i, subject_type="csp", subject_id=1, target_type="talking_point",
                                    target_key=f"old{i}", kind="check_theirs", text="SECRET-SUGGESTION-TEXT",
                                    verdict="useful"))
    db.commit()
    for row in db.query(IntelligenceFeedback).filter(IntelligenceFeedback.target_key.like("old%")).all():
        row.updated_at = NOW - timedelta(days=731)
    db.commit()
    summary = retention.run_nightly(db)
    db.expire_all()
    assert summary["feedback"] == 2
    assert db.query(IntelligenceFeedback).count() == 3                       # the recent ones stay
    entry = [a for a in db.query(AuditLog).all() if a.action == "intelligence.feedback_purged"][0]
    assert entry.after["count"] == 2 and "SECRET-SUGGESTION-TEXT" not in str(entry.after)
