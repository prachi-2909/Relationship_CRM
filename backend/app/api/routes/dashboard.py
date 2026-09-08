"""A single roll-up for the executive dashboard."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.engagement_moment import EngagementMoment, MomentStatus
from ...models.official import Official, OfficialStatus
from ...models.organization_unit import OrganizationUnit, OrgUnitStatus
from ...models.relationship import Relationship, RiskLevel
from ...models.task import Task, TaskStatus
from ...models.user import User
from ...security.deps import get_current_user
from ...services.scoring import band

settings = get_settings()

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    now = datetime.now(timezone.utc)

    officials = db.scalar(
        select(func.count())
        .select_from(Official)
        .where(Official.status == OfficialStatus.ACTIVE)
    ) or 0
    units = db.scalar(
        select(func.count())
        .select_from(OrganizationUnit)
        .where(OrganizationUnit.status == OrgUnitStatus.ACTIVE)
    ) or 0

    scores = db.scalars(select(Relationship.score)).all()
    total_rel = len(scores)
    avg_health = round(sum(scores) / total_rel) if total_rel else 0
    at_risk = db.scalar(
        select(func.count())
        .select_from(Relationship)
        .where(Relationship.risk_level == RiskLevel.HIGH)
    ) or 0

    overdue_filter = [
        Task.status == TaskStatus.OPEN,
        Task.due_at.is_not(None),
        Task.due_at < now,
    ]
    overdue = db.scalar(
        select(func.count()).select_from(Task).where(*overdue_filter)
    ) or 0
    my_overdue = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(*overdue_filter, Task.assigned_to == user.id)
    ) or 0

    drafts_pending = db.scalar(
        select(func.count())
        .select_from(EngagementMoment)
        .where(EngagementMoment.status == MomentStatus.DRAFT_READY)
    ) or 0
    moments_open = db.scalar(
        select(func.count())
        .select_from(EngagementMoment)
        .where(
            EngagementMoment.status.in_(
                [MomentStatus.DETECTED, MomentStatus.DRAFT_READY, MomentStatus.APPROVED]
            )
        )
    ) or 0

    bands: dict[str, int] = {"Strong": 0, "Healthy": 0, "Attention required": 0, "At risk": 0}
    for score in scores:
        bands[band(score)[0]] += 1

    return {
        "officials": officials,
        "units": units,
        "relationships": total_rel,
        "average_health": avg_health,
        "at_risk": at_risk,
        "overdue_followups": overdue,
        "my_overdue_followups": my_overdue,
        "drafts_pending": drafts_pending,
        "moments_open": moments_open,
        "health_bands": bands,
        "moments_enabled": settings.enable_moments,
    }
