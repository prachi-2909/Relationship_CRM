from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.models.agent import AgentRecommendation, RecommendationStatus
from app.models.opportunity import Opportunity
from app.models.user import Role
from app.services import agent as agent_service


def _admin(make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")


def _active_relationship(client, name="A Rao"):
    official = client.post("/api/v1/officials", json={"name": name}).json()
    rel = client.post("/api/v1/relationships", json={"official_id": official["id"]}).json()
    client.post(f"/api/v1/relationships/{rel['id']}/claim")
    client.patch(f"/api/v1/relationships/{rel['id']}", json={"status": "active"})
    return official, rel


def _log_commitment(client, relationship_id):
    """A note the stub extractor will pull a commitment out of, with nothing else
    (no negative/positive sentiment, no greeting moment) so the agent's stub
    recommends exactly one CREATE_TASK via the 'open commitment' path."""
    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": relationship_id,
            "type": "call",
            "raw_notes": "We will share the report by Monday.",
        },
    )


def _log_opportunity_signal(client, relationship_id):
    """A note the stub extractor reads as a potential opportunity (same
    _OPPORTUNITY_HINTS vocabulary used for both interaction-level detection
    and the agent's Brief scan)."""
    client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": relationship_id,
            "type": "call",
            "raw_notes": "They are interested in a new current account for their subsidiary.",
        },
    )


def _verified_birthday_soon(client, official_id):
    soon = (date.today() + timedelta(days=3)).replace(year=1980)
    d = client.put(
        f"/api/v1/officials/{official_id}/dates/birthday",
        json={"value": soon.isoformat(), "source": "manual entry"},
    ).json()
    client.post(f"/api/v1/officials/{official_id}/dates/{d['id']}/verify")


def test_kill_switch_blocks_a_run(client, make_user, login, monkeypatch):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    monkeypatch.setattr(agent_service.settings, "enable_agent", False)

    resp = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    )
    assert resp.status_code == 409


def test_relationship_run_recommends_a_task_from_an_open_commitment(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    assert run["status"] == "completed"
    assert run["relationships_considered"] == 1
    assert run["recommendations_created"] >= 1

    recs = run["recommendations"]
    task_recs = [r for r in recs if r["type"] == "create_task"]
    assert len(task_recs) == 1
    assert task_recs[0]["status"] == "pending"

    detail = client.get(f"/api/v1/agent/recommendations/{task_recs[0]['id']}").json()
    assert "commitment" in detail["reasoning"].lower()
    assert detail["evidence"]


def test_approving_create_task_creates_a_real_task(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    rec_id = next(r["id"] for r in run["recommendations"] if r["type"] == "create_task")

    approved = client.post(f"/api/v1/agent/recommendations/{rec_id}/approve").json()
    assert approved["status"] == "approved"
    assert approved["result_ref"]["task_id"]

    tasks = client.get("/api/v1/tasks", params={"relationship_id": rel["id"]}).json()
    assert tasks["total"] == 1

    # a second approval attempt is rejected - it's already decided
    assert client.post(f"/api/v1/agent/recommendations/{rec_id}/approve").status_code == 409


def test_reject_has_no_domain_side_effect(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    rec_id = next(r["id"] for r in run["recommendations"] if r["type"] == "create_task")

    rejected = client.post(
        f"/api/v1/agent/recommendations/{rec_id}/reject", json={"reason": "not needed"}
    ).json()
    assert rejected["status"] == "rejected"
    assert rejected["result_ref"] == {"reason": "not needed"}

    tasks = client.get("/api/v1/tasks", params={"relationship_id": rel["id"]}).json()
    assert tasks["total"] == 0


def test_draft_moment_recommendation_only_targets_a_real_detected_moment(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _verified_birthday_soon(client, official["id"])
    client.post("/api/v1/moments/detect")

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    moment_recs = [r for r in run["recommendations"] if r["type"] == "draft_moment"]
    assert len(moment_recs) == 1

    detail = client.get(f"/api/v1/agent/recommendations/{moment_recs[0]['id']}").json()
    moment_id = detail["payload"]["moment_id"]
    moment_before = client.get(f"/api/v1/moments/{moment_id}").json()
    assert moment_before["status"] == "detected"
    assert moment_before["draft_text"] is None

    approved = client.post(f"/api/v1/agent/recommendations/{moment_recs[0]['id']}/approve").json()
    assert approved["result_ref"]["moment_id"] == moment_id

    moment_after = client.get(f"/api/v1/moments/{moment_id}").json()
    assert moment_after["status"] == "draft_ready"
    assert moment_after["draft_text"]


def test_portfolio_run_respects_the_per_run_cap(client, make_user, login, monkeypatch):
    _admin(make_user, login)
    _, rel1 = _active_relationship(client, "Official One")
    _, rel2 = _active_relationship(client, "Official Two")
    _log_commitment(client, rel1["id"])
    _log_commitment(client, rel2["id"])

    monkeypatch.setattr(agent_service.settings, "agent_max_relationships_per_run", 1)
    run = client.post("/api/v1/agent/runs", json={"scope": "portfolio"}).json()

    assert run["relationships_considered"] == 1
    assert run["recommendations_created"] == 1


def test_no_duplicate_pending_recommendation_on_a_second_run(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])

    first = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    assert first["recommendations_created"] >= 1

    second = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    assert second["recommendations_created"] == 0

    recs = client.get(
        "/api/v1/agent/recommendations",
        params={"relationship_id": rel["id"], "type": "create_task"},
    ).json()
    assert recs["total"] == 1


def test_approver_viewer_cannot_trigger_or_approve(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="v@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("admin@example.com", "secret123")
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])
    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    rec_id = run["recommendations"][0]["id"]

    login("v@example.com", "secret123")
    assert (
        client.post(
            "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
        ).status_code
        == 403
    )
    assert client.post(f"/api/v1/agent/recommendations/{rec_id}/approve").status_code == 403


def test_rm_cannot_trigger_a_run_on_a_relationship_they_do_not_own(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    login("admin@example.com", "secret123")
    official, rel = _active_relationship(client)  # claimed by admin

    login("rm@example.com", "secret123")
    resp = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    )
    assert resp.status_code == 403


def test_nightly_sweep_expires_stale_pending_recommendations(client, make_user, login, db):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])
    client.post("/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]})

    rec = db.scalars(
        select(AgentRecommendation).where(AgentRecommendation.relationship_id == rel["id"])
    ).one()
    rec.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    expired = agent_service.expire_stale_recommendations(db)
    db.commit()
    assert expired == 1

    db.refresh(rec)
    assert rec.status == RecommendationStatus.EXPIRED


def test_agent_skips_create_opportunity_when_one_is_already_open(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_opportunity_signal(client, rel["id"])

    # the interaction pipeline's own detection already suggested one - open,
    # even though its title won't exactly match whatever the agent would
    # have proposed
    presuggested = client.get(
        "/api/v1/opportunities", params={"relationship_id": rel["id"]}
    ).json()
    assert presuggested["total"] == 1
    assert presuggested["items"][0]["status"] == "suggested"

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    opp_recs = [r for r in run["recommendations"] if r["type"] == "create_opportunity"]
    assert opp_recs == []


def test_agent_recommends_and_creates_an_opportunity_once_none_is_open(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_opportunity_signal(client, rel["id"])

    suggested = client.get(
        "/api/v1/opportunities", params={"relationship_id": rel["id"]}
    ).json()["items"][0]
    # a human decided it wasn't real - dismissed is not "open" anymore
    client.patch(f"/api/v1/opportunities/{suggested['id']}", json={"status": "dismissed"})

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    opp_recs = [r for r in run["recommendations"] if r["type"] == "create_opportunity"]
    assert len(opp_recs) == 1

    approved = client.post(f"/api/v1/agent/recommendations/{opp_recs[0]['id']}/approve").json()
    assert approved["status"] == "approved"
    assert approved["result_ref"]["opportunity_id"]

    after = client.get("/api/v1/opportunities", params={"relationship_id": rel["id"]}).json()
    confirmed = [o for o in after["items"] if o["status"] == "confirmed"]
    assert len(confirmed) == 1
    assert confirmed[0]["id"] == approved["result_ref"]["opportunity_id"]


def test_agent_flags_a_stalled_confirmed_opportunity_with_a_follow_up_task(
    client, make_user, login, db
):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    created = client.post(
        "/api/v1/opportunities", json={"relationship_id": rel["id"], "title": "Term loan renewal"}
    ).json()

    opp = db.get(Opportunity, created["id"])
    opp.created_at = datetime.now(timezone.utc) - timedelta(days=20)
    db.commit()

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    task_recs = [r for r in run["recommendations"] if r["type"] == "create_task"]
    assert len(task_recs) == 1
    assert "Term loan renewal" in task_recs[0]["reasoning"]

    approved = client.post(f"/api/v1/agent/recommendations/{task_recs[0]['id']}/approve").json()
    assert approved["result_ref"]["task_id"]


def test_agent_does_not_flag_a_suggested_or_fresh_opportunity(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    # freshly created and still SUGGESTED (not confirmed) - neither should trigger
    client.post(
        "/api/v1/opportunities", json={"relationship_id": rel["id"], "title": "Fresh confirmed one"}
    )

    run = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    task_recs = [r for r in run["recommendations"] if r["type"] == "create_task"]
    assert task_recs == []


def test_agent_respects_a_recent_rejection_then_forgets_it_after_cooldown(
    client, make_user, login, db
):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])

    first = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    rec_id = next(r["id"] for r in first["recommendations"] if r["type"] == "create_task")
    client.post(f"/api/v1/agent/recommendations/{rec_id}/reject", json={"reason": "not now"})

    # rejected moments ago - a second run should NOT immediately re-propose it
    second = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    assert [r for r in second["recommendations"] if r["type"] == "create_task"] == []

    # push the rejection outside the cooldown window - it should surface again
    rec = db.get(AgentRecommendation, rec_id)
    rec.decided_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()

    third = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    assert any(r["type"] == "create_task" for r in third["recommendations"])


def test_agent_history_is_recorded_as_a_tool_used_on_the_next_run(client, make_user, login):
    _admin(make_user, login)
    official, rel = _active_relationship(client)
    _log_commitment(client, rel["id"])

    first = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    assert "agent_history" not in first["tools_used"]  # nothing decided yet
    rec_id = first["recommendations"][0]["id"]
    client.post(f"/api/v1/agent/recommendations/{rec_id}/reject", json={"reason": "not now"})

    second = client.get(f"/api/v1/agent/runs/{first['id']}").json()
    assert second["id"] == first["id"]  # sanity: same run, unaffected retroactively

    # a fresh run now has a decided recommendation in its history
    third = client.post(
        "/api/v1/agent/runs", json={"scope": "relationship", "relationship_id": rel["id"]}
    ).json()
    assert "agent_history" in third["tools_used"]
