"""Strategic memory: evidence-backed insights, computed from real historical
data via plain SQL aggregates - never an LLM guess, never invented. Below
the minimum sample size, no insight is created at all (None, not a weak
guess). Response-rate insights use a documented proxy signal (a subsequent
inbound interaction) since the schema has no ground-truth "they replied"
field - that proxy is always labeled in the stored evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.agent import AgentRecommendation, RecommendationStatus
from ..models.engagement_moment import EngagementMoment, MomentStatus
from ..models.interaction import Direction, Interaction
from ..models.strategic_insight import StrategicInsight
from ..models.task import Task, TaskStatus

settings = get_settings()

_MIN_SAMPLE_SIZE = 5
_MOMENT_RESPONSE_WINDOW_DAYS = 14


@dataclass
class InsightResult:
    statement: str
    metric_type: str
    sample_size: int
    evidence: dict


def compute_task_completion_rate(db: Session, official_id: int) -> InsightResult | None:
    total_terminal = db.scalar(
        select(func.count(Task.id))
        .where(Task.official_id == official_id)
        .where(Task.status.in_((TaskStatus.DONE, TaskStatus.CANCELLED)))
    ) or 0
    if total_terminal < _MIN_SAMPLE_SIZE:
        return None
    done = db.scalar(
        select(func.count(Task.id))
        .where(Task.official_id == official_id)
        .where(Task.status == TaskStatus.DONE)
    ) or 0
    rate = done / total_terminal
    return InsightResult(
        statement=(
            f"{done} of {total_terminal} follow-up tasks for this official were completed "
            f"({rate:.0%}) in the recorded sample."
        ),
        metric_type="task_completion_rate",
        sample_size=total_terminal,
        evidence={"done": done, "total_terminal": total_terminal, "rate": round(rate, 4)},
    )


def compute_moment_response_rate(db: Session, official_id: int) -> InsightResult | None:
    sent = db.scalars(
        select(EngagementMoment)
        .where(EngagementMoment.official_id == official_id)
        .where(EngagementMoment.status == MomentStatus.SENT_MANUALLY)
        .where(EngagementMoment.decided_at.is_not(None))
    ).all()
    if len(sent) < _MIN_SAMPLE_SIZE:
        return None
    responded = 0
    for moment in sent:
        window_end = moment.decided_at + timedelta(days=_MOMENT_RESPONSE_WINDOW_DAYS)
        has_inbound = db.scalar(
            select(Interaction.id)
            .where(Interaction.official_id == official_id)
            .where(Interaction.direction == Direction.INBOUND)
            .where(Interaction.occurred_at > moment.decided_at)
            .where(Interaction.occurred_at <= window_end)
        )
        if has_inbound is not None:
            responded += 1
    rate = responded / len(sent)
    return InsightResult(
        statement=(
            f"{responded} of {len(sent)} engagement-moment messages sent to this official "
            f"were followed by an inbound interaction within {_MOMENT_RESPONSE_WINDOW_DAYS} "
            f"days ({rate:.0%}) in the recorded sample."
        ),
        metric_type="moment_response_rate",
        sample_size=len(sent),
        evidence={
            "responded": responded,
            "total_sent": len(sent),
            "rate": round(rate, 4),
            "window_days": _MOMENT_RESPONSE_WINDOW_DAYS,
            "proxy_signal": True,
            "proxy_description": "a subsequent inbound interaction stands in for a confirmed reply",
        },
    )


def compute_recommendation_approval_rate(db: Session, official_id: int) -> InsightResult | None:
    decided = db.scalar(
        select(func.count(AgentRecommendation.id))
        .where(AgentRecommendation.official_id == official_id)
        .where(AgentRecommendation.status.in_((RecommendationStatus.APPROVED, RecommendationStatus.REJECTED)))
    ) or 0
    if decided < _MIN_SAMPLE_SIZE:
        return None
    approved = db.scalar(
        select(func.count(AgentRecommendation.id))
        .where(AgentRecommendation.official_id == official_id)
        .where(AgentRecommendation.status == RecommendationStatus.APPROVED)
    ) or 0
    rate = approved / decided
    return InsightResult(
        statement=(
            f"{approved} of {decided} agent recommendations for this official were approved "
            f"({rate:.0%}) in the recorded sample."
        ),
        metric_type="recommendation_approval_rate",
        sample_size=decided,
        evidence={"approved": approved, "decided": decided, "rate": round(rate, 4)},
    )


_COMPUTERS = (
    compute_task_completion_rate,
    compute_moment_response_rate,
    compute_recommendation_approval_rate,
)


def _store(db: Session, official_id: int, result: InsightResult) -> None:
    existing = db.scalars(
        select(StrategicInsight)
        .where(StrategicInsight.official_id == official_id)
        .where(StrategicInsight.metric_type == result.metric_type)
        .where(StrategicInsight.superseded.is_(False))
    ).all()
    for row in existing:
        row.superseded = True
    db.add(
        StrategicInsight(
            scope_type="official",
            official_id=official_id,
            statement=result.statement,
            metric_type=result.metric_type,
            sample_size=result.sample_size,
            evidence=result.evidence,
            computed_at=datetime.now(timezone.utc),
            superseded=False,
        )
    )


def recompute_for_official(db: Session, official_id: int) -> int:
    if not settings.enable_strategic_insights:
        return 0
    created = 0
    for compute in _COMPUTERS:
        result = compute(db, official_id)
        if result is not None:
            _store(db, official_id, result)
            created += 1
    db.flush()
    return created


def recompute_all(db: Session) -> int:
    """Nightly job entry point - recompute for every official who has any
    task/moment/recommendation activity at all (cheap to over-include; the
    per-official computers themselves gate on minimum sample size)."""
    if not settings.enable_strategic_insights:
        return 0
    official_ids = set(db.scalars(select(Task.official_id).distinct()))
    official_ids |= set(db.scalars(select(EngagementMoment.official_id).distinct()))
    official_ids |= set(db.scalars(select(AgentRecommendation.official_id).distinct()))
    total = 0
    for official_id in official_ids:
        total += recompute_for_official(db, official_id)
    return total


def latest_for_official(db: Session, official_id: int, *, limit: int = 3) -> list[StrategicInsight]:
    return list(
        db.scalars(
            select(StrategicInsight)
            .where(StrategicInsight.official_id == official_id)
            .where(StrategicInsight.superseded.is_(False))
            .order_by(StrategicInsight.computed_at.desc())
            .limit(limit)
        )
    )
