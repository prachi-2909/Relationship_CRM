"""Near-duplicate commitments: flagged for a human, never merged silently, nothing lost, and genuinely
different tasks are never flagged."""

from datetime import date, datetime, timedelta, timezone

from app.models.audit import AuditLog
from app.models.call_intelligence import CallAIAnalysis, CallSession
from app.models.commitment import Commitment, CommitmentEvent, CommitmentSourceKind, CommitmentStatus
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import commitments as svc

NOW = datetime.now(timezone.utc)


def _csp(db, csp_id, rm):
    c = Csp(csp_id=csp_id, name="Agent " + csp_id, rm_name="RM", rm_user_id=rm.id, mobile="9000000021",
            category="Gold CSP", status=CspStatus.ACTIVE)
    db.add(c)
    db.commit()
    return c


def _call(db, user, csp, brief, days_ago=0):
    call = CallSession(dc_user_id=user.id, direction=Direction.OUTBOUND, phone_ref="9000000021",
                       started_at=NOW - timedelta(days=days_ago), csp_id=csp.id)
    db.add(call)
    db.flush()
    db.add(CallAIAnalysis(call_session_id=call.id, analysis_json=brief))
    db.commit()
    db.refresh(call)
    return call


def _rows(db):
    db.expire_all()
    return db.query(Commitment).order_by(Commitment.id).all()


def _events(db, c):
    db.expire_all()
    return [e.action for e in db.query(CommitmentEvent).filter_by(commitment_id=c.id).order_by(CommitmentEvent.id)]


# --------------------------------------------------------------------------- flagging, not merging


def test_a_reworded_repeat_in_the_same_brief_is_flagged_but_both_are_kept(db, make_user):
    rm = make_user(email="d1@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "D1", rm)
    call = _call(db, rm, csp, {
        "commitments": ["CSP to fix the terminal expiry issue as soon as possible."],
        "action_items": ["CSP commits to fixing the terminal expiry issue (no specific deadline given)."],
    })
    svc.extract_from_call(db, call)
    db.commit()
    first, second = _rows(db)
    assert len(_rows(db)) == 2                                  # nothing dropped
    assert first.duplicate_review is None and first.possible_duplicate_of_id is None
    assert second.duplicate_review == "flagged" and second.possible_duplicate_of_id == first.id
    assert first.status == second.status == CommitmentStatus.PROPOSED   # and nothing was auto-closed


def test_genuinely_different_tasks_are_not_flagged(db, make_user):
    rm = make_user(email="d2@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "D2", rm)
    call = _call(db, rm, csp, {"commitments": [
        "CSP to complete the remaining 3 PMSBY enrollments.",
        "CSP to complete the remaining 2 PMJJBY enrollments.",
        "RM to call the CSP on Monday.",
        "RM to call the CSP on Friday.",
        "RM to call Rakesh about the terminal expiry issue.",
        "RM to call Suresh about the terminal expiry issue.",
    ]})
    svc.extract_from_call(db, call)
    db.commit()
    assert len(_rows(db)) == 6
    assert all(c.duplicate_review is None for c in _rows(db))


def test_different_due_dates_are_not_duplicates(db, make_user):
    rm = make_user(email="d3@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "D3", rm)
    call = _call(db, rm, csp, {"commitments": [
        "CSP to send the sales report by 2026-12-05.", "CSP to send the sales report by 2026-12-20.",
    ]})
    svc.extract_from_call(db, call)
    db.commit()
    assert all(c.duplicate_review is None for c in _rows(db))


def test_a_repeat_on_a_later_call_is_flagged_against_the_earlier_one_whatever_its_state(db, make_user):
    rm = make_user(email="d4@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "D4", rm)
    text = "CSP to share the updated performance report."
    c1 = _call(db, rm, csp, {"commitments": [text]}, days_ago=10)
    svc.extract_from_call(db, c1)
    db.commit()
    original = _rows(db)[0]
    svc.set_status(db, original, CommitmentStatus.OPEN, rm)
    svc.set_status(db, original, CommitmentStatus.DONE, rm)          # the earlier one is already DONE
    c2 = _call(db, rm, csp, {"commitments": ["CSP will send the updated performance report."]})
    svc.extract_from_call(db, c2)
    db.commit()
    later = _rows(db)[1]
    assert later.possible_duplicate_of_id == original.id and later.duplicate_review == "flagged"


def test_the_same_wording_for_a_different_csp_is_not_a_duplicate(db, make_user):
    rm = make_user(email="d5@example.com", role=Role.RELATIONSHIP_MANAGER)
    a, b = _csp(db, "D5A", rm), _csp(db, "D5B", rm)
    for csp in (a, b):
        svc.extract_from_call(db, _call(db, rm, csp, {"commitments": ["CSP to fix the terminal expiry issue."]}))
    db.commit()
    assert all(c.duplicate_review is None for c in _rows(db))


def test_a_manually_added_commitment_that_repeats_an_open_one_is_flagged(db, make_user):
    rm = make_user(email="d6@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "D6", rm)
    first = svc.add_manual(db, csp=csp, text="RM to send the slab chart.", party=svc.CommitmentParty.OURS,
                           due_date=None, actor=rm)
    again = svc.add_manual(db, csp=csp, text="RM will share the slab chart.", party=svc.CommitmentParty.OURS,
                           due_date=None, actor=rm)
    db.refresh(again)
    assert again.possible_duplicate_of_id == first.id and again.duplicate_review == "flagged"


# --------------------------------------------------------------------------- human review


def _flagged_pair(db, rm, csp_id="DR"):
    csp = _csp(db, csp_id, rm)
    c1 = _call(db, rm, csp, {"commitments": ["CSP to fix the terminal expiry issue by 2026-12-05."]}, days_ago=5)
    svc.extract_from_call(db, c1)
    c2 = _call(db, rm, csp, {"commitments": ["CSP will repair the terminal expiry problem by 2026-12-05."]})
    svc.extract_from_call(db, c2)
    db.commit()
    first, second = [r for r in _rows(db) if r.csp_id == csp.id]
    assert second.duplicate_review == "flagged"
    return csp, first, second, c1, c2


def test_merge_closes_the_repeat_but_keeps_both_rows_with_owner_due_date_and_source_call(db, make_user):
    rm = make_user(email="r1@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm, "DR1")
    svc.set_status(db, first, CommitmentStatus.OPEN, rm)                  # the earlier one was accepted
    svc.set_status(db, second, CommitmentStatus.OPEN, rm)                 # and so was the repeat
    before = (first.status, first.due_date, first.owner_user_id, first.call_session_id, first.text)

    svc.review_duplicate(db, second, "merge", rm)
    db.expire_all()
    first, second = _rows(db)
    assert len(_rows(db)) == 2                                            # nothing deleted
    assert (first.status, first.due_date, first.owner_user_id, first.call_session_id, first.text) == before
    assert second.status == CommitmentStatus.CANCELLED and second.merged_into_id == first.id
    assert second.duplicate_review == "merged"
    assert second.call_session_id == c2.id and second.owner_user_id == rm.id      # the repeat keeps its own
    assert second.due_date == date(2026, 12, 5)                                    # source, owner and due date
    folded = svc.commitment_dict(db, first)["also_mentioned"]
    assert folded == [{"id": second.id, "due_date": "2026-12-05", "source_call_id": c2.id, "owner_user_id": rm.id}]


def test_merge_history_keeps_the_acceptance_and_who_did_what(db, make_user):
    rm = make_user(email="r2@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm, "DR2")
    svc.set_status(db, second, CommitmentStatus.OPEN, rm)
    svc.review_duplicate(db, second, "merge", rm)
    assert _events(db, second) == ["proposed", "possible_duplicate", "accepted", "merged"]
    assert "absorbed_duplicate" in _events(db, first)
    trail = svc.history(db, second)
    assert [e["actor_id"] for e in trail if e["action"] in ("accepted", "merged")] == [rm.id, rm.id]
    assert all("text" not in e["detail"] for e in trail)                  # history never copies commitment text


def test_a_dismissal_is_recorded_with_who_and_when(db, make_user):
    rm = make_user(email="r3@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "DR3", rm)
    svc.extract_from_call(db, _call(db, rm, csp, {"commitments": ["CSP to do X later."]}))
    db.commit()
    c = _rows(db)[0]
    svc.set_status(db, c, CommitmentStatus.CANCELLED, rm)
    (proposed, dismissed) = svc.history(db, c)
    assert proposed["action"] == "proposed" and dismissed["action"] == "dismissed"
    assert dismissed["actor_id"] == rm.id and dismissed["at"]


def test_separate_clears_the_flag_keeps_both_and_survives_reprocessing(db, make_user):
    rm = make_user(email="r4@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm, "DR4")
    svc.review_duplicate(db, second, "separate", rm)
    db.expire_all()
    assert _rows(db)[1].duplicate_review == "separate"
    assert "kept_separate" in _events(db, second)
    svc.extract_from_call(db, c2)                                         # the same brief is processed again
    db.commit()
    rows = _rows(db)
    assert len(rows) == 2 and rows[1].duplicate_review == "separate" and rows[1].id == second.id


def test_unreviewed_flagged_proposals_are_refreshed_by_a_new_brief_without_leaving_dangling_links(db, make_user):
    rm = make_user(email="r5@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm, "DR5")
    c2.analysis.analysis_json = {"commitments": ["CSP to do something completely different."]}
    db.commit()
    svc.extract_from_call(db, c2)
    db.commit()
    rows = _rows(db)
    assert [r.text for r in rows][-1] == "CSP to do something completely different."
    assert all(r.possible_duplicate_of_id in (None, first.id) for r in rows)
    # SQLite may hand the deleted row's id to the new commitment; none of the OLD row's history
    # ("possible_duplicate", ...) may follow that id - only the new row's own "proposed" event exists.
    assert _events(db, rows[-1]) == ["proposed"]


def test_review_rules_are_enforced(db, make_user):
    rm = make_user(email="r6@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm, "DR6")
    import pytest

    with pytest.raises(ValueError):
        svc.review_duplicate(db, first, "merge", rm)                      # not flagged
    with pytest.raises(ValueError):
        svc.review_duplicate(db, second, "banana", rm)
    svc.set_status(db, second, CommitmentStatus.OPEN, rm)
    svc.set_status(db, second, CommitmentStatus.DONE, rm)
    with pytest.raises(ValueError):
        svc.review_duplicate(db, second, "merge", rm)                     # a finished one is not merged away
    csp2, a, b, *_ = _flagged_pair(db, make_user(email="r6b@example.com", role=Role.RELATIONSHIP_MANAGER), "DR6B")
    svc.review_duplicate(db, b, "merge", rm)
    with pytest.raises(ValueError):
        svc.set_status(db, b, CommitmentStatus.OPEN, rm)                  # a merged row cannot be reopened


def test_a_dismissed_original_pulls_the_merged_repeat_into_the_dismissed_state(db, make_user):
    rm = make_user(email="r7@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm, "DR7")
    svc.set_status(db, first, CommitmentStatus.CANCELLED, rm)             # the human had rejected the original
    svc.review_duplicate(db, second, "merge", rm)                         # "this repeat is the same thing"
    db.expire_all()
    assert _rows(db)[1].status == CommitmentStatus.CANCELLED              # so it is not offered again


# --------------------------------------------------------------------------- lifecycle keeps links clean


def test_purging_a_commitment_removes_its_history_and_nulls_links_pointing_at_it(db, make_user):
    rm = make_user(email="l1@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm, "DL1")
    svc.set_status(db, first, CommitmentStatus.CANCELLED, rm)
    first.updated_at = NOW - timedelta(days=800)                          # closed long ago
    db.commit()
    result = svc.apply_lifecycle(db)
    db.commit()
    db.expire_all()
    assert result["closed_purged"] == 1
    assert db.query(CommitmentEvent).filter_by(commitment_id=first.id).count() == 0
    survivor = db.get(Commitment, second.id)
    assert survivor is not None and survivor.possible_duplicate_of_id is None   # no dangling pointer


# --------------------------------------------------------------------------- API + access


def _api_setup(db, make_user):
    rm_a = make_user(email="api-a@example.com", role=Role.RELATIONSHIP_MANAGER)
    rm_b = make_user(email="api-b@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp, first, second, c1, c2 = _flagged_pair(db, rm_a, "API1")
    return rm_a, rm_b, csp, first, second


def test_precall_shows_the_possible_duplicate_for_review(client, db, make_user, login):
    rm_a, _, csp, first, second = _api_setup(db, make_user)
    login("api-a@example.com", "password123")
    body = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()
    flagged = [p for p in body["proposed_commitments"] if p.get("possible_duplicate")]
    assert len(flagged) == 1
    dup = flagged[0]["possible_duplicate"]
    assert dup["id"] == first.id and dup["text"] == first.text and dup["source_call_id"] == first.call_session_id
    assert len(body["proposed_commitments"]) == 2                          # both still listed - nothing hidden


def test_merge_and_separate_through_the_api(client, db, make_user, login):
    rm_a, _, csp, first, second = _api_setup(db, make_user)
    login("api-a@example.com", "password123")
    url = f"/api/v1/csps/commitments/{second.id}/duplicate"
    assert client.post(url, json={"decision": "banana"}).status_code == 400
    merged = client.post(url, json={"decision": "merge"})
    assert merged.status_code == 200 and merged.json()["status"] == "cancelled"
    assert client.post(url, json={"decision": "merge"}).status_code == 400   # already ruled on
    pre = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()
    assert [p["id"] for p in pre["proposed_commitments"]] == [first.id]
    hist = client.get(f"/api/v1/csps/commitments/{second.id}/history").json()
    assert [e["action"] for e in hist["events"]][-1] == "merged"
    assert any(a.action == "commitment.merged" for a in db.query(AuditLog).all())


def test_another_rm_cannot_review_or_read_history_of_my_csps_commitments(client, db, make_user, login):
    rm_a, rm_b, csp, first, second = _api_setup(db, make_user)
    login("api-b@example.com", "password123")
    assert client.post(f"/api/v1/csps/commitments/{second.id}/duplicate", json={"decision": "merge"}).status_code == 404
    assert client.get(f"/api/v1/csps/commitments/{second.id}/history").status_code == 404
    db.expire_all()
    assert db.get(Commitment, second.id).duplicate_review == "flagged"      # untouched


def test_an_rm_cannot_touch_an_sbi_officials_commitment_through_the_csp_routes(client, db, make_user, make_official, login):
    rm = make_user(email="hole-rm@example.com", role=Role.RELATIONSHIP_MANAGER)
    admin = make_user(email="hole-admin@example.com", role=Role.ADMIN)
    official = make_official("Some Official")
    c = Commitment(official_id=official.id, text="Official to send the list.",
                   status=CommitmentStatus.OPEN, source_kind=CommitmentSourceKind.DC_OFFICIAL,
                   party=svc.CommitmentParty.THEIRS)
    db.add(c)
    db.commit()
    for who in ("hole-rm@example.com", "hole-admin@example.com"):
        login(who, "password123")
        assert client.post(f"/api/v1/csps/commitments/{c.id}/status", json={"status": "done"}).status_code == 404
        assert client.post(f"/api/v1/csps/commitments/{c.id}/duplicate", json={"decision": "merge"}).status_code == 404
        assert client.get(f"/api/v1/csps/commitments/{c.id}/history").status_code == 404
        client.post("/api/v1/auth/logout")
    db.expire_all()
    assert db.get(Commitment, c.id).status == CommitmentStatus.OPEN


def test_outcome_is_recorded_when_a_commitment_is_closed_as_not_fulfilled(client, db, make_user, login):
    rm = make_user(email="oc@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, "OC1", rm)
    svc.extract_from_call(db, _call(db, rm, csp, {"commitments": ["CSP to deliver the signed forms."]}))
    db.commit()
    cid = _rows(db)[0].id
    login("oc@example.com", "password123")
    url = f"/api/v1/csps/commitments/{cid}/status"
    assert client.post(url, json={"status": "open"}).status_code == 200
    assert client.post(url, json={"status": "cancelled", "outcome": "banana"}).status_code == 400
    assert client.post(url, json={"status": "cancelled", "outcome": "not_fulfilled"}).status_code == 200
    events = client.get(f"/api/v1/csps/commitments/{cid}/history").json()["events"]
    assert events[-1]["action"] == "cancelled" and events[-1]["detail"]["outcome"] == "not_fulfilled"
