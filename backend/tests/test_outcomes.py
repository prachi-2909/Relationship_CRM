from datetime import datetime, timedelta, timezone

from app.models.agent import (
    AgentRecommendation,
    AgentRun,
    AgentRunScope,
    AgentRunStatus,
    AgentTrigger,
    RecommendationStatus,
    RecommendationType,
    RiskTier,
)
from app.models.engagement_moment import EngagementMoment, MomentStatus, MomentType
from app.models.opportunity import Opportunity, OpportunityStage, OpportunityStatus
from app.models.outcome import OutcomeStatus, RecommendationOutcome
from app.models.relationship import Relationship
from app.models.task import Task, TaskStatus
from app.services import outcomes


def _rel(db, official_id: int) -> Relationship:
    rel = Relationship(official_id=official_id)
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def _run(db, rel: Relationship, user) -> AgentRun:
    run = AgentRun(
        trigger=AgentTrigger.MANUAL, scope=AgentRunScope.RELATIONSHIP, relationship_id=rel.id,
        requested_by=user.id, status=AgentRunStatus.COMPLETED, model="stub", tools_used=[],
        relationships_considered=1, recommendations_created=1, started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


def _approved_rec(db, rel, official_id, run, rec_type, result_ref):
    rec = AgentRecommendation(
        run_id=run.id, relationship_id=rel.id, official_id=official_id,
        type=rec_type, risk_tier=RiskTier.LOW, reasoning="test", evidence={}, payload={},
        status=RecommendationStatus.APPROVED, decided_at=datetime.now(timezone.utc), result_ref=result_ref,
    )
    db.add(rec)
    db.flush()
    return rec


# --- create_missing_outcomes -----------------------------------------------


def test_create_missing_outcomes_backfills_pending_row(db, make_official, make_user):
    official = make_official(name="Backfill")
    rel = _rel(db, official.id)
    user = make_user(email="bf@example.com")
    run = _run(db, rel, user)
    task = Task(relationship_id=rel.id, official_id=official.id, title="x", status=TaskStatus.OPEN)
    db.add(task)
    db.flush()
    rec = _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_TASK, {"task_id": task.id})
    db.commit()

    created = outcomes.create_missing_outcomes(db)
    db.commit()
    assert created == 1
    outcome = db.query(RecommendationOutcome).filter_by(recommendation_id=rec.id).one()
    assert outcome.status == OutcomeStatus.PENDING
    assert outcome.tracked_object_type == "task"

    # idempotent - doesn't double-create
    again = outcomes.create_missing_outcomes(db)
    assert again == 0


def test_create_missing_outcomes_skips_untrackable(db, make_official, make_user):
    official = make_official(name="Untrackable")
    rel = _rel(db, official.id)
    user = make_user(email="ut@example.com")
    run = _run(db, rel, user)
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_TASK, None)
    db.commit()
    assert outcomes.create_missing_outcomes(db) == 0


# --- verdict rules: task -----------------------------------------------------


def test_task_done_on_time_is_positive(db, make_official, make_user):
    official = make_official(name="OnTime")
    rel = _rel(db, official.id)
    user = make_user(email="ot@example.com")
    run = _run(db, rel, user)
    due = datetime.now(timezone.utc) + timedelta(days=1)
    task = Task(
        relationship_id=rel.id, official_id=official.id, title="x", status=TaskStatus.DONE,
        due_at=due, completed_at=due - timedelta(hours=1),
    )
    db.add(task)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_TASK, {"task_id": task.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=task.id).one()
    assert outcome.status == OutcomeStatus.POSITIVE
    assert outcome.resolved_at is not None


def test_task_done_late_is_neutral(db, make_official, make_user):
    official = make_official(name="Late")
    rel = _rel(db, official.id)
    user = make_user(email="late@example.com")
    run = _run(db, rel, user)
    due = datetime.now(timezone.utc) - timedelta(days=1)
    task = Task(
        relationship_id=rel.id, official_id=official.id, title="x", status=TaskStatus.DONE,
        due_at=due, completed_at=due + timedelta(days=2),
    )
    db.add(task)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_TASK, {"task_id": task.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=task.id).one()
    assert outcome.status == OutcomeStatus.NEUTRAL


def test_task_cancelled_is_negative(db, make_official, make_user):
    official = make_official(name="Cancelled")
    rel = _rel(db, official.id)
    user = make_user(email="cancel@example.com")
    run = _run(db, rel, user)
    task = Task(relationship_id=rel.id, official_id=official.id, title="x", status=TaskStatus.CANCELLED)
    db.add(task)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_TASK, {"task_id": task.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=task.id).one()
    assert outcome.status == OutcomeStatus.NEGATIVE


def test_task_still_open_stays_pending(db, make_official, make_user):
    official = make_official(name="StillOpen")
    rel = _rel(db, official.id)
    user = make_user(email="open@example.com")
    run = _run(db, rel, user)
    task = Task(relationship_id=rel.id, official_id=official.id, title="x", status=TaskStatus.OPEN)
    db.add(task)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_TASK, {"task_id": task.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=task.id).one()
    assert outcome.status == OutcomeStatus.PENDING
    assert outcome.resolved_at is None


def test_task_open_past_abandon_window_is_negative(db, make_official, make_user):
    official = make_official(name="Abandoned")
    rel = _rel(db, official.id)
    user = make_user(email="aband@example.com")
    run = _run(db, rel, user)
    due = datetime.now(timezone.utc) - timedelta(days=31)
    task = Task(relationship_id=rel.id, official_id=official.id, title="x", status=TaskStatus.OPEN, due_at=due)
    db.add(task)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_TASK, {"task_id": task.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=task.id).one()
    assert outcome.status == OutcomeStatus.NEGATIVE


# --- verdict rules: opportunity ---------------------------------------------


def test_opportunity_won_is_positive(db, make_official, make_user):
    official = make_official(name="Won")
    rel = _rel(db, official.id)
    user = make_user(email="won@example.com")
    run = _run(db, rel, user)
    opp = Opportunity(
        relationship_id=rel.id, official_id=official.id, title="Deal", source="test",
        status=OpportunityStatus.CONFIRMED, stage=OpportunityStage.WON,
    )
    db.add(opp)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_OPPORTUNITY, {"opportunity_id": opp.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=opp.id).one()
    assert outcome.status == OutcomeStatus.POSITIVE


def test_opportunity_lost_is_negative(db, make_official, make_user):
    official = make_official(name="Lost")
    rel = _rel(db, official.id)
    user = make_user(email="lost@example.com")
    run = _run(db, rel, user)
    opp = Opportunity(
        relationship_id=rel.id, official_id=official.id, title="Deal", source="test",
        status=OpportunityStatus.CONFIRMED, stage=OpportunityStage.LOST,
    )
    db.add(opp)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_OPPORTUNITY, {"opportunity_id": opp.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=opp.id).one()
    assert outcome.status == OutcomeStatus.NEGATIVE


# --- verdict rules: moment ---------------------------------------------------


def test_moment_dismissed_is_negative(db, make_official, make_user):
    official = make_official(name="MomentDismissed")
    rel = _rel(db, official.id)
    user = make_user(email="momdis@example.com")
    run = _run(db, rel, user)
    moment = EngagementMoment(
        official_id=official.id, relationship_id=rel.id, type=MomentType.BIRTHDAY,
        status=MomentStatus.DISMISSED, evidence={},
    )
    db.add(moment)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.DRAFT_MOMENT, {"moment_id": moment.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()
    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=moment.id).one()
    assert outcome.status == OutcomeStatus.NEGATIVE


# --- history preserved, never overwritten -----------------------------------


def test_resolved_outcome_is_not_re_evaluated(db, make_official, make_user):
    official = make_official(name="Fixed")
    rel = _rel(db, official.id)
    user = make_user(email="fixed@example.com")
    run = _run(db, rel, user)
    opp = Opportunity(
        relationship_id=rel.id, official_id=official.id, title="Deal", source="test",
        status=OpportunityStatus.CONFIRMED, stage=OpportunityStage.WON,
    )
    db.add(opp)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_OPPORTUNITY, {"opportunity_id": opp.id})
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()

    # flip the opportunity to lost after the outcome already resolved positive
    opp.stage = OpportunityStage.LOST
    db.commit()
    outcomes.reconcile_pending(db)  # only touches PENDING rows
    db.commit()

    outcome = db.query(RecommendationOutcome).filter_by(tracked_object_id=opp.id).one()
    assert outcome.status == OutcomeStatus.POSITIVE  # unchanged - history preserved


# --- evaluation metrics ------------------------------------------------------


def test_list_outcomes_route(client, make_user, login, db, make_official):
    from app.models.user import Role as _Role

    user = make_user(email="listout@example.com", password="secret123", role=_Role.ADMIN)
    login("listout@example.com", "secret123")
    official = make_official(name="ListOutcome")
    rel = _rel(db, official.id)
    run = _run(db, rel, user)
    opp = Opportunity(
        relationship_id=rel.id, official_id=official.id, title="Deal", source="test",
        status=OpportunityStatus.CONFIRMED, stage=OpportunityStage.WON,
    )
    db.add(opp)
    db.flush()
    _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_OPPORTUNITY, {"opportunity_id": opp.id})
    db.commit()
    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()

    resp = client.get("/api/v1/agent/outcomes")
    assert resp.status_code == 200
    assert any(o["tracked_object_id"] == opp.id for o in resp.json())


def test_compute_metrics_with_no_data(db):
    metrics = outcomes.compute_metrics(db)
    assert metrics["total_decided"] == 0
    assert metrics["approval_rate"] is None
    assert metrics["positive_outcome_rate"] is None


def test_compute_metrics_approval_and_outcome_rates(db, make_official, make_user):
    official = make_official(name="Metrics")
    rel = _rel(db, official.id)
    user = make_user(email="metrics@example.com")
    run = _run(db, rel, user)

    for i in range(3):
        opp = Opportunity(
            relationship_id=rel.id, official_id=official.id, title=f"Deal {i}", source="test",
            status=OpportunityStatus.CONFIRMED,
            stage=OpportunityStage.WON if i < 2 else OpportunityStage.LOST,
        )
        db.add(opp)
        db.flush()
        _approved_rec(db, rel, official.id, run, RecommendationType.CREATE_OPPORTUNITY, {"opportunity_id": opp.id})
    rejected = AgentRecommendation(
        run_id=run.id, relationship_id=rel.id, official_id=official.id,
        type=RecommendationType.CREATE_TASK, risk_tier=RiskTier.LOW, reasoning="x", evidence={}, payload={},
        status=RecommendationStatus.REJECTED, decided_at=datetime.now(timezone.utc),
    )
    db.add(rejected)
    db.commit()

    outcomes.create_missing_outcomes(db)
    outcomes.reconcile_pending(db)
    db.commit()

    metrics = outcomes.compute_metrics(db)
    assert metrics["total_decided"] == 4
    assert metrics["approval_rate"] == 0.75
    assert metrics["resolved_outcomes"] == 3
    assert round(metrics["positive_outcome_rate"], 2) == round(2 / 3, 2)
