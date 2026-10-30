"""The CSP relationship score: relationship, business and overall, each from plain arithmetic with a reason in words."""

import json
from datetime import date, datetime, timedelta, timezone

from app.models.call_intelligence import CallSession, CallSessionStatus
from app.models.commitment import Commitment, CommitmentParty, CommitmentSourceKind, CommitmentStatus
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import csp_scoring, llm, tara_check

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def _csp(db, rm, code="K-SCORE"):
    c = Csp(csp_id=code, name="Score CSP", rm_name="RM", rm_user_id=rm.id, mobile="9000000055",
            category="Gold CSP", branch_name="BR", status=CspStatus.ACTIVE)
    db.add(c)
    db.commit()
    return c


def _rm(make_user, email):
    return make_user(email=email, password="secret123", role=Role.RELATIONSHIP_MANAGER)


def _call(db, rm, csp, *, days_ago, status=CallSessionStatus.REVIEW_REQUIRED, reported=True):
    started = NOW - timedelta(days=days_ago)
    db.add(CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9000000055", csp_id=csp.id,
                       started_at=started, ended_at=started + timedelta(minutes=2) if reported else None,
                       processing_status=status))
    db.commit()


def _commitment(db, rm, csp, *, status, due, done=None, created_days_ago=10):
    c = Commitment(csp_id=csp.id, owner_user_id=rm.id, text="x", party=CommitmentParty.OURS, due_date=due,
                   status=status, source_kind=CommitmentSourceKind.RM_CSP,
                   done_at=done)
    c.created_at = NOW - timedelta(days=created_days_ago)
    db.add(c)
    db.commit()


def test_a_csp_with_no_history_scores_zero_on_contact_and_says_why(db, make_user):
    csp = _csp(db, _rm(make_user, "rm-score-0@example.com"))
    s = csp_scoring.score_csp(db, csp, now=NOW)

    assert s["overall"] == 0 and s["relationship"] == 0 and s["business"] is None
    assert s["band"] == "At risk" and s["tara_included"] is False
    assert s["reasons"] == ["No call with this CSP is on record."]
    assert s["components"]["answered"]["value"] is None and s["components"]["followthrough"]["value"] is None


def test_contact_recency_falls_to_zero_over_30_days(db, make_user):
    rm = _rm(make_user, "rm-score-rec@example.com")
    csp = _csp(db, rm)
    _call(db, rm, csp, days_ago=15)
    comp = csp_scoring.score_csp(db, csp, now=NOW)["components"]["recency"]
    assert comp["value"] == 50.0 and comp["note"] == "Last call was 15 days ago."

    _call(db, rm, csp, days_ago=0)                     # a call today resets it
    assert csp_scoring.score_csp(db, csp, now=NOW)["components"]["recency"]["value"] == 100.0


def test_a_cancelled_call_is_not_contact(db, make_user):
    rm = _rm(make_user, "rm-score-can@example.com")
    csp = _csp(db, rm)
    _call(db, rm, csp, days_ago=1, status=CallSessionStatus.CANCELLED)
    assert csp_scoring.score_csp(db, csp, now=NOW)["components"]["recency"]["value"] == 0.0


def test_answered_counts_only_reported_attempts(db, make_user):
    rm = _rm(make_user, "rm-score-ans@example.com")
    csp = _csp(db, rm)
    for d in (1, 2, 3):
        _call(db, rm, csp, days_ago=d)                                                      # picked up
    _call(db, rm, csp, days_ago=4, status=CallSessionStatus.CANCELLED)                      # rang out unanswered
    _call(db, rm, csp, days_ago=5, status=CallSessionStatus.CANCELLED, reported=False)      # never reported: ignored
    _call(db, rm, csp, days_ago=200)                                                        # outside the window: ignored
    comp = csp_scoring.score_csp(db, csp, now=NOW)["components"]["answered"]
    assert comp["value"] == 75.0 and "3 of 4" in comp["note"]


def test_follow_through_counts_kept_late_and_overdue_and_skips_what_is_not_yet_due(db, make_user):
    rm = _rm(make_user, "rm-score-ft@example.com")
    csp = _csp(db, rm)
    today = NOW.date()
    _commitment(db, rm, csp, status=CommitmentStatus.DONE, due=today, done=NOW)                          # on time
    _commitment(db, rm, csp, status=CommitmentStatus.DONE, due=today - timedelta(days=5), done=NOW)      # late
    _commitment(db, rm, csp, status=CommitmentStatus.OPEN, due=today - timedelta(days=2))                # overdue
    _commitment(db, rm, csp, status=CommitmentStatus.OPEN, due=today + timedelta(days=9))                # not due: left out
    _commitment(db, rm, csp, status=CommitmentStatus.CANCELLED, due=today - timedelta(days=9))           # left out
    comp = csp_scoring.score_csp(db, csp, now=NOW)["components"]["followthrough"]
    assert comp["value"] == 50.0                                  # (1 + 0.5) / 3
    assert comp["note"] == "Commitments: 1 kept on time, 1 done late, 1 overdue."


def test_a_missing_signal_shares_its_weight_over_the_rest(db, make_user):
    rm = _rm(make_user, "rm-score-w@example.com")
    csp = _csp(db, rm)
    _call(db, rm, csp, days_ago=0)                                                     # recency 100, answered 100
    _commitment(db, rm, csp, status=CommitmentStatus.OPEN, due=NOW.date() - timedelta(days=1))   # follow-through 0
    s = csp_scoring.score_csp(db, csp, now=NOW)
    # relationship = (100*20 + 100*10 + 0*20) / 50 = 60 ; no TARA yet, so overall equals relationship
    assert s["relationship"] == 60 and s["business"] is None and s["overall"] == 60
    assert s["band"] == "Healthy"


def test_the_business_part_uses_tara_when_it_is_mapped(db, make_user, monkeypatch):
    rm = _rm(make_user, "rm-score-biz@example.com")
    csp = _csp(db, rm)
    _call(db, rm, csp, days_ago=0)
    monkeypatch.setattr(csp_scoring, "_tara_performance", lambda tara: (40.0, "PMJJBY at 40% of target."))
    monkeypatch.setattr(csp_scoring, "_tara_trend", lambda tara: (80.0, "Transactions up on last month."))

    s = csp_scoring.score_csp(db, csp, now=NOW, tara=[{"tool": "x"}])

    assert s["business"] == 56                                     # (40*30 + 80*20) / 50
    assert s["relationship"] == 100 and s["tara_included"] is True
    assert s["overall"] == round((100 * 20 + 100 * 10 + 40 * 30 + 80 * 20) / 80)
    assert s["reasons"][0] == "PMJJBY at 40% of target."          # the weakest signal is read first


def test_the_same_records_always_give_the_same_score(db, make_user):
    rm = _rm(make_user, "rm-score-det@example.com")
    csp = _csp(db, rm)
    _call(db, rm, csp, days_ago=7)
    assert csp_scoring.score_csp(db, csp, now=NOW) == csp_scoring.score_csp(db, csp, now=NOW)


def test_the_weights_add_up_and_every_signal_belongs_to_one_part():
    assert sum(csp_scoring.WEIGHTS.values()) == 100
    grouped = [n for names in csp_scoring.GROUPS.values() for n in names]
    assert sorted(grouped) == sorted(csp_scoring.WEIGHTS)


def test_the_pre_call_briefing_carries_the_score(client, db, make_user, login):
    rm = _rm(make_user, "rm-score-api@example.com")
    csp = _csp(db, rm)
    login("rm-score-api@example.com", "secret123")
    body = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()
    assert set(body["score"]) >= {"overall", "relationship", "business", "band", "tara_included", "components", "reasons"}
    assert body["score"]["version"] == csp_scoring.WEIGHTS_VERSION


def test_the_supervisor_is_given_the_score_without_the_internals(client, db, make_user, login, monkeypatch):
    rm = _rm(make_user, "rm-score-ask@example.com")
    csp = _csp(db, rm)
    monkeypatch.setattr(tara_check, "gather", lambda q, code: [])
    seen = {}
    monkeypatch.setattr(llm, "chat", lambda system, user, **k: seen.update(system=system, user=user) or "ok")
    login("rm-score-ask@example.com", "secret123")

    client.post("/api/v1/ask", json={"question": "Score CSP ka relationship kaisa hai?"})

    assert '"relationship_score"' in seen["user"] and "relationship_score" in seen["system"]
    payload = json.loads(seen["user"].split("Data:\n", 1)[1])
    score = payload["data"][0]["relationship_score"]
    assert set(score) == {"overall", "relationship", "business", "band", "tara_included", "reasons"}
