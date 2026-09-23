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
from app.models.relationship import Relationship
from app.models.task import Task, TaskStatus
from app.services import strategic_insight


def _rel(db, official_id: int) -> Relationship:
    rel = Relationship(official_id=official_id)
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def _task(db, rel: Relationship, status: TaskStatus) -> Task:
    task = Task(relationship_id=rel.id, official_id=rel.official_id, title="Follow up", status=status)
    db.add(task)
    return task


def test_below_minimum_sample_returns_none(db, make_official):
    official = make_official(name="Sparse")
    rel = _rel(db, official.id)
    for _ in range(2):
        _task(db, rel, TaskStatus.DONE)
    db.commit()
    assert strategic_insight.compute_task_completion_rate(db, official.id) is None


def test_task_completion_rate_computed_with_enough_sample(db, make_official):
    official = make_official(name="Busy")
    rel = _rel(db, official.id)
    for _ in range(4):
        _task(db, rel, TaskStatus.DONE)
    _task(db, rel, TaskStatus.CANCELLED)
    db.commit()

    result = strategic_insight.compute_task_completion_rate(db, official.id)
    assert result is not None
    assert result.sample_size == 5
    assert result.evidence["done"] == 4
    assert "proxy_signal" not in result.evidence


def test_recommendation_approval_rate(db, make_official, make_user):
    official = make_official(name="Recommended")
    rel = _rel(db, official.id)
    user = make_user(email="approver@example.com")
    run = AgentRun(
        trigger=AgentTrigger.MANUAL, scope=AgentRunScope.RELATIONSHIP, relationship_id=rel.id,
        requested_by=user.id, status=AgentRunStatus.COMPLETED, model="stub", tools_used=[],
        relationships_considered=1, recommendations_created=5, started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    for i in range(5):
        rec = AgentRecommendation(
            run_id=run.id, relationship_id=rel.id, official_id=official.id,
            type=RecommendationType.CREATE_TASK, risk_tier=RiskTier.LOW,
            reasoning="test", evidence={}, payload={},
            status=RecommendationStatus.APPROVED if i < 3 else RecommendationStatus.REJECTED,
            decided_by=user.id, decided_at=datetime.now(timezone.utc),
        )
        db.add(rec)
    db.commit()

    result = strategic_insight.compute_recommendation_approval_rate(db, official.id)
    assert result is not None
    assert result.sample_size == 5
    assert result.evidence["approved"] == 3


def test_moment_response_rate_is_labeled_as_proxy(db, make_official):
    from app.models.engagement_moment import EngagementMoment, MomentStatus, MomentType
    from app.models.interaction import Direction, Interaction, InteractionType

    official = make_official(name="Moment Target")
    rel = _rel(db, official.id)
    now = datetime.now(timezone.utc)
    for i in range(5):
        # spaced far apart so each moment's response window doesn't overlap
        # another moment's - otherwise one reply could count for several
        sent_at = now - timedelta(days=30 * (i + 1))
        moment = EngagementMoment(
            official_id=official.id, relationship_id=rel.id, type=MomentType.BIRTHDAY,
            status=MomentStatus.SENT_MANUALLY, decided_at=sent_at, evidence={},
        )
        db.add(moment)
        if i < 2:
            db.add(
                Interaction(
                    relationship_id=rel.id, official_id=official.id, type=InteractionType.NOTE,
                    direction=Direction.INBOUND, occurred_at=sent_at + timedelta(days=2),
                    raw_notes="thanks!",
                )
            )
    db.commit()

    result = strategic_insight.compute_moment_response_rate(db, official.id)
    assert result is not None
    assert result.evidence["proxy_signal"] is True
    assert result.evidence["responded"] == 2


def test_recompute_for_official_stores_and_supersedes(db, make_official):
    official = make_official(name="Recomputed")
    rel = _rel(db, official.id)
    for _ in range(5):
        _task(db, rel, TaskStatus.DONE)
    db.commit()

    created = strategic_insight.recompute_for_official(db, official.id)
    db.commit()
    assert created >= 1
    first_pass = strategic_insight.latest_for_official(db, official.id)
    assert len(first_pass) == created

    # add one more cancelled task, changing the rate, and recompute again
    _task(db, rel, TaskStatus.CANCELLED)
    db.commit()
    strategic_insight.recompute_for_official(db, official.id)
    db.commit()

    current = strategic_insight.latest_for_official(db, official.id)
    completion_insights = [i for i in current if i.metric_type == "task_completion_rate"]
    assert len(completion_insights) == 1  # only the non-superseded one is returned
    assert completion_insights[0].evidence["total_terminal"] == 6


def test_disabled_returns_zero(db, make_official, monkeypatch):
    official = make_official(name="Disabled")
    rel = _rel(db, official.id)
    for _ in range(5):
        _task(db, rel, TaskStatus.DONE)
    db.commit()

    monkeypatch.setattr(strategic_insight.settings, "enable_strategic_insights", False)
    assert strategic_insight.recompute_for_official(db, official.id) == 0
