"""Recommendation outcomes: deterministic verdicts on what happened after an
agent recommendation was approved - never an LLM guess. Wired into the
existing nightly job, same pattern as agent.expire_stale_recommendations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.agent import AgentRecommendation, RecommendationStatus, RecommendationType
from ..models.engagement_moment import EngagementMoment, MomentStatus
from ..models.interaction import Direction, Interaction
from ..models.opportunity import Opportunity, OpportunityStage
from ..models.outcome import OutcomeStatus, RecommendationOutcome
from ..models.task import Task, TaskStatus
from . import audit

_TASK_ABANDON_DAYS = 30
_MOMENT_RESPONSE_WINDOW_DAYS = 14

_TRACKED_OBJECT_BY_TYPE = {
    RecommendationType.CREATE_TASK: ("task", "task_id"),
    RecommendationType.DRAFT_MOMENT: ("moment", "moment_id"),
    RecommendationType.CREATE_OPPORTUNITY: ("opportunity", "opportunity_id"),
}


def create_missing_outcomes(db: Session) -> int:
    """Lazily backfill a pending outcome row for any APPROVED recommendation
    that has a trackable result_ref and doesn't have one yet."""
    tracked_ids = set(db.scalars(select(RecommendationOutcome.recommendation_id)))
    recs = db.scalars(
        select(AgentRecommendation).where(AgentRecommendation.status == RecommendationStatus.APPROVED)
    ).all()
    created = 0
    now = datetime.now(timezone.utc)
    for rec in recs:
        if rec.id in tracked_ids:
            continue
        mapping = _TRACKED_OBJECT_BY_TYPE.get(rec.type)
        if mapping is None or not rec.result_ref:
            continue
        object_type, key = mapping
        object_id = rec.result_ref.get(key)
        if object_id is None:
            continue
        db.add(
            RecommendationOutcome(
                recommendation_id=rec.id,
                tracked_object_type=object_type,
                tracked_object_id=object_id,
                status=OutcomeStatus.PENDING,
                checked_at=now,
                detail={},
            )
        )
        created += 1
    db.flush()
    return created


def _verdict_for_task(db: Session, task_id: int) -> tuple[OutcomeStatus, dict, bool]:
    task = db.get(Task, task_id)
    if task is None:
        return OutcomeStatus.INCONCLUSIVE, {"reason": "task no longer exists"}, True
    if task.status == TaskStatus.DONE:
        on_time = task.due_at is None or (task.completed_at is not None and task.completed_at <= task.due_at)
        status = OutcomeStatus.POSITIVE if on_time else OutcomeStatus.NEUTRAL
        return status, {"task_status": "done", "on_time": on_time}, True
    if task.status == TaskStatus.CANCELLED:
        return OutcomeStatus.NEGATIVE, {"task_status": "cancelled"}, True
    if task.due_at is not None:
        abandon_by = task.due_at + timedelta(days=_TASK_ABANDON_DAYS)
        if datetime.now(timezone.utc) > abandon_by:
            return OutcomeStatus.NEGATIVE, {"task_status": "open", "abandoned": True}, True
    return OutcomeStatus.PENDING, {"task_status": "open"}, False


def _verdict_for_moment(db: Session, moment_id: int) -> tuple[OutcomeStatus, dict, bool]:
    moment = db.get(EngagementMoment, moment_id)
    if moment is None:
        return OutcomeStatus.INCONCLUSIVE, {"reason": "moment no longer exists"}, True
    if moment.status == MomentStatus.DISMISSED:
        return OutcomeStatus.NEGATIVE, {"moment_status": "dismissed"}, True
    if moment.status == MomentStatus.SENT_MANUALLY and moment.decided_at is not None:
        window_end = moment.decided_at + timedelta(days=_MOMENT_RESPONSE_WINDOW_DAYS)
        has_inbound = db.scalar(
            select(Interaction.id)
            .where(Interaction.official_id == moment.official_id)
            .where(Interaction.direction == Direction.INBOUND)
            .where(Interaction.occurred_at > moment.decided_at)
            .where(Interaction.occurred_at <= window_end)
        )
        detail = {"moment_status": "sent_manually", "proxy_signal": True}
        if has_inbound is not None:
            return OutcomeStatus.POSITIVE, detail, True
        if datetime.now(timezone.utc) > window_end:
            return OutcomeStatus.NEUTRAL, detail, True
        return OutcomeStatus.PENDING, detail, False
    return OutcomeStatus.PENDING, {"moment_status": moment.status.value}, False


def _verdict_for_opportunity(db: Session, opportunity_id: int) -> tuple[OutcomeStatus, dict, bool]:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        return OutcomeStatus.INCONCLUSIVE, {"reason": "opportunity no longer exists"}, True
    if opp.stage == OpportunityStage.WON:
        return OutcomeStatus.POSITIVE, {"opportunity_stage": "won"}, True
    if opp.stage == OpportunityStage.LOST:
        return OutcomeStatus.NEGATIVE, {"opportunity_stage": "lost"}, True
    return OutcomeStatus.PENDING, {"opportunity_stage": opp.stage.value}, False


_VERDICT_FUNCS = {
    "task": _verdict_for_task,
    "moment": _verdict_for_moment,
    "opportunity": _verdict_for_opportunity,
}


def reconcile_pending(db: Session) -> int:
    """Apply verdict rules to every pending outcome, updating status/detail
    and stamping resolved_at + auditing on a terminal transition."""
    pending = db.scalars(
        select(RecommendationOutcome).where(RecommendationOutcome.status == OutcomeStatus.PENDING)
    ).all()
    resolved = 0
    for outcome in pending:
        verdict_func = _VERDICT_FUNCS.get(outcome.tracked_object_type)
        if verdict_func is None:
            continue
        status, detail, is_terminal = verdict_func(db, outcome.tracked_object_id)
        outcome.checked_at = datetime.now(timezone.utc)
        outcome.detail = detail
        if is_terminal and status != OutcomeStatus.PENDING:
            outcome.status = status
            outcome.resolved_at = datetime.now(timezone.utc)
            audit.record(
                db,
                action="agent.outcome.resolved",
                entity_type="recommendation_outcome",
                entity_id=outcome.id,
                after={"status": status.value, "detail": detail},
            )
            resolved += 1
    db.flush()
    return resolved


def compute_metrics(
    db: Session,
    *,
    rec_type: RecommendationType | None = None,
    risk_tier=None,
    since=None,
    relationship_ids: list[int] | None = None,
) -> dict:
    query = select(AgentRecommendation).where(
        AgentRecommendation.status.in_((RecommendationStatus.APPROVED, RecommendationStatus.REJECTED))
    )
    if rec_type is not None:
        query = query.where(AgentRecommendation.type == rec_type)
    if risk_tier is not None:
        query = query.where(AgentRecommendation.risk_tier == risk_tier)
    if since is not None:
        query = query.where(AgentRecommendation.created_at >= since)
    if relationship_ids is not None:
        query = query.where(AgentRecommendation.relationship_id.in_(relationship_ids))
    decided = db.scalars(query).all()

    total_decided = len(decided)
    approved = [r for r in decided if r.status == RecommendationStatus.APPROVED]
    approval_rate = len(approved) / total_decided if total_decided else None

    outcomes = []
    if approved:
        rec_ids = [r.id for r in approved]
        outcomes = db.scalars(
            select(RecommendationOutcome).where(RecommendationOutcome.recommendation_id.in_(rec_ids))
        ).all()
    resolved_outcomes = [o for o in outcomes if o.status not in (OutcomeStatus.PENDING,)]
    positive = [o for o in resolved_outcomes if o.status == OutcomeStatus.POSITIVE]
    positive_outcome_rate = len(positive) / len(resolved_outcomes) if resolved_outcomes else None

    resolution_days = [
        (o.resolved_at - o.recommendation.decided_at).total_seconds() / 86400
        for o in resolved_outcomes
        if o.resolved_at is not None and o.recommendation.decided_at is not None
    ]
    resolution_days.sort()
    median_days = resolution_days[len(resolution_days) // 2] if resolution_days else None

    return {
        "total_decided": total_decided,
        "approval_rate": approval_rate,
        "resolved_outcomes": len(resolved_outcomes),
        "positive_outcome_rate": positive_outcome_rate,
        "median_days_to_resolution": median_days,
    }
