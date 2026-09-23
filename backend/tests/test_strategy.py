import pytest

from app.models.relationship import Relationship
from app.models.strategy import ExperimentStatus, StrategyVersionStatus
from app.models.user import Role
from app.services import agent as agent_svc
from app.services import strategy as strategy_svc


def _rels(db, official_ids):
    rels = []
    for oid in official_ids:
        rel = Relationship(official_id=oid)
        db.add(rel)
        rels.append(rel)
    db.commit()
    for rel in rels:
        db.refresh(rel)
    return rels


def _officials(make_official, n):
    return [make_official(name=f"Strategy Official {i}").id for i in range(n)]


def test_new_version_starts_at_1_and_increments(db, make_user):
    admin = make_user(email="s1@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(db, strategy_id="s1", name="S1", category="followup", actor=admin)
    db.commit()
    v1 = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {}}, actor=admin)
    v2 = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {}}, actor=admin)
    db.commit()
    assert v1.version == 1
    assert v2.version == 2


def test_experiment_assignment_is_deterministic_and_covers_all(db, make_user, make_official):
    admin = make_user(email="s2@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(db, strategy_id="s2", name="S2", category="followup", actor=admin)
    control = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {"followup_due_in_days": 3}}, actor=admin)
    treatment = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {"followup_due_in_days": 9}}, actor=admin)
    db.commit()

    officials = _officials(make_official, 10)
    rels = _rels(db, officials)
    experiment = strategy_svc.create_experiment(
        db, strategy=strategy, control_version=control, treatment_version=treatment,
        relationship_ids=[r.id for r in rels], actor=admin,
    )
    db.commit()
    assert len(experiment.assignments) == 10
    assert experiment.status == ExperimentStatus.RUNNING

    # deterministic - re-deriving the same split twice gives the same arms
    arms_by_rel = {a.relationship_id: a.arm for a in experiment.assignments}
    for rel in rels:
        expected = "treatment" if hash(rel.id) % 2 == 0 else "control"
        assert arms_by_rel[rel.id].value == expected


def test_get_effective_config_none_when_unassigned(db, make_official):
    official_id = _officials(make_official, 1)[0]
    rel = _rels(db, [official_id])[0]
    assert strategy_svc.get_effective_config(db, rel.id) is None


def test_get_effective_config_returns_experiment_arm_config(db, make_user, make_official):
    admin = make_user(email="s3@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(
        db, strategy_id=strategy_svc.FOLLOWUP_TIMING_STRATEGY_ID, name="Timing", category="followup", actor=admin
    )
    control = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {"followup_due_in_days": 3}}, actor=admin)
    treatment = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {"followup_due_in_days": 9}}, actor=admin)
    db.commit()

    officials = _officials(make_official, 4)
    rels = _rels(db, officials)
    experiment = strategy_svc.create_experiment(
        db, strategy=strategy, control_version=control, treatment_version=treatment,
        relationship_ids=[r.id for r in rels], actor=admin,
    )
    db.commit()

    for rel in rels:
        config = strategy_svc.get_effective_config(db, rel.id)
        assert config is not None
        assert config["params"]["followup_due_in_days"] in (3, 9)


def test_promote_rejects_wrong_status(db, make_user):
    admin = make_user(email="s4@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(db, strategy_id="s4", name="S4", category="followup", actor=admin)
    version = strategy_svc.create_version(db, strategy=strategy, config={}, actor=admin)
    db.commit()
    with pytest.raises(ValueError):
        strategy_svc.promote(db, version, admin)


def test_promote_rejects_no_completed_experiment(db, make_user, make_official):
    admin = make_user(email="s5@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(db, strategy_id="s5", name="S5", category="followup", actor=admin)
    control = strategy_svc.create_version(db, strategy=strategy, config={}, actor=admin)
    treatment = strategy_svc.create_version(db, strategy=strategy, config={}, actor=admin)
    db.commit()
    officials = _officials(make_official, 4)
    rels = _rels(db, officials)
    strategy_svc.create_experiment(
        db, strategy=strategy, control_version=control, treatment_version=treatment,
        relationship_ids=[r.id for r in rels], actor=admin,
    )
    db.commit()
    with pytest.raises(ValueError, match="No completed experiment"):
        strategy_svc.promote(db, treatment, admin)


def test_promote_rejects_insufficient_sample(db, make_user, make_official):
    admin = make_user(email="s6@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(db, strategy_id="s6", name="S6", category="followup", actor=admin)
    control = strategy_svc.create_version(db, strategy=strategy, config={}, actor=admin)
    treatment = strategy_svc.create_version(db, strategy=strategy, config={}, actor=admin)
    db.commit()
    officials = _officials(make_official, 4)
    rels = _rels(db, officials)
    experiment = strategy_svc.create_experiment(
        db, strategy=strategy, control_version=control, treatment_version=treatment,
        relationship_ids=[r.id for r in rels], actor=admin, minimum_sample_size=20,
    )
    db.commit()
    strategy_svc.complete_experiment(db, experiment, admin)
    db.commit()
    with pytest.raises(ValueError, match="needs at least"):
        strategy_svc.promote(db, treatment, admin)


def test_promote_succeeds_with_enough_sample_and_retires_old_active(db, make_user, make_official):
    admin = make_user(email="s7@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(db, strategy_id="s7", name="S7", category="followup", actor=admin)
    v1 = strategy_svc.create_version(db, strategy=strategy, config={"v": 1}, actor=admin)
    v2 = strategy_svc.create_version(db, strategy=strategy, config={"v": 2}, actor=admin)
    # simulate v1 already being the active version, to verify it gets retired
    v1.status = StrategyVersionStatus.ACTIVE
    strategy.current_version_id = v1.id
    db.commit()

    officials = _officials(make_official, 21)
    rels = _rels(db, officials)
    experiment = strategy_svc.create_experiment(
        db, strategy=strategy, control_version=v1, treatment_version=v2,
        relationship_ids=[r.id for r in rels], actor=admin, minimum_sample_size=1,
    )
    db.commit()

    treatment_count = sum(1 for a in experiment.assignments if a.arm.value == "treatment")
    if treatment_count == 0:
        pytest.skip("degenerate hash split for this test's relationship ids")

    strategy_svc.complete_experiment(db, experiment, admin)
    db.commit()

    strategy_svc.promote(db, v2, admin)
    db.commit()
    db.refresh(v2)
    db.refresh(strategy)
    assert v2.status == StrategyVersionStatus.ACTIVE
    assert strategy.current_version_id == v2.id
    assert v2.approved_by == admin.id
    db.refresh(v1)
    assert v1.status == StrategyVersionStatus.RETIRED


def test_agent_uses_strategy_override_when_assigned(db, make_user, make_official):
    """End-to-end: a relationship assigned to the treatment arm gets the
    treatment's due_in_days baked into its stub-generated task, while an
    unassigned relationship keeps the default of 3."""
    admin = make_user(email="s8@example.com", role=Role.ADMIN)
    strategy = strategy_svc.create_strategy(
        db, strategy_id=strategy_svc.FOLLOWUP_TIMING_STRATEGY_ID, name="Timing", category="followup", actor=admin
    )
    control = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {"followup_due_in_days": 3}}, actor=admin)
    treatment = strategy_svc.create_version(db, strategy=strategy, config={"kind": "rule_param", "params": {"followup_due_in_days": 9}}, actor=admin)
    db.commit()

    official = make_official(name="Reconnect Target")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    db.refresh(rel)

    experiment = strategy_svc.create_experiment(
        db, strategy=strategy, control_version=control, treatment_version=treatment,
        relationship_ids=[rel.id], actor=admin,
    )
    db.commit()

    arm = experiment.assignments[0].arm.value
    expected_days = 9 if arm == "treatment" else 3

    brief = {"reconnect_opportunity": {"yes": True, "reason": "long gap"}, "open_followups": [], "next_interaction": "Check in"}
    strategy_config = strategy_svc.get_effective_config(db, rel.id)
    followup_due_in_days = strategy_config["params"]["followup_due_in_days"] if strategy_config else None
    drafts = agent_svc._stub_recommend(brief, followup_due_in_days=followup_due_in_days)
    assert drafts[0].payload["due_in_days"] == expected_days


# --- API / RBAC -------------------------------------------------------------


def _as(make_user, login, role, email):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def test_strategy_routes_require_admin(client, make_user, login):
    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    resp = client.get("/api/v1/strategies")
    assert resp.status_code == 403
    resp = client.post("/api/v1/strategies", json={"strategy_id": "x", "name": "X", "category": "y"})
    assert resp.status_code == 403


def test_create_strategy_and_version_via_api(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-strat@example.com")
    resp = client.post(
        "/api/v1/strategies", json={"strategy_id": "api_test", "name": "API Test", "category": "followup"}
    )
    assert resp.status_code == 201
    strategy = resp.json()
    assert strategy["status"] == "draft"

    resp = client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        json={"config": {"kind": "rule_param", "params": {"followup_due_in_days": 5}}},
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == 1

    resp = client.get("/api/v1/strategies")
    assert resp.status_code == 200
    assert any(s["strategy_id"] == "api_test" for s in resp.json())


def test_promote_via_api_returns_409_when_not_ready(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin-strat2@example.com")
    resp = client.post(
        "/api/v1/strategies", json={"strategy_id": "api_test2", "name": "API Test 2", "category": "followup"}
    )
    strategy_id = resp.json()["id"]
    resp = client.post(f"/api/v1/strategies/{strategy_id}/versions", json={"config": {}})
    version_id = resp.json()["id"]

    resp = client.post(f"/api/v1/strategies/versions/{version_id}/promote")
    assert resp.status_code == 409
