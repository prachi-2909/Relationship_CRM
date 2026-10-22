"""A single roll-up for the executive dashboard."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.call_intelligence import CallSession, CallVoiceNote
from ...models.csp import Csp, CspStatus
from ...models.engagement_moment import EngagementMoment, MomentStatus
from ...models.official import Official, OfficialStatus
from ...models.opportunity import Opportunity, OpportunityStage, OpportunityStatus
from ...models.organization_unit import OrganizationUnit, OrgUnitStatus
from ...models.relationship import Relationship, RiskLevel
from ...models.task import Task, TaskStatus
from ...models.user import Role, User
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

    opportunities_suggested = db.scalar(
        select(func.count())
        .select_from(Opportunity)
        .where(Opportunity.status == OpportunityStatus.SUGGESTED)
    ) or 0
    open_pipeline_stages = (
        OpportunityStage.IDENTIFIED,
        OpportunityStage.QUALIFIED,
        OpportunityStage.PROPOSAL,
        OpportunityStage.NEGOTIATION,
    )
    opportunity_stage_counts: dict[str, int] = {}
    for stage in open_pipeline_stages:
        opportunity_stage_counts[stage.value] = db.scalar(
            select(func.count())
            .select_from(Opportunity)
            .where(Opportunity.status == OpportunityStatus.CONFIRMED)
            .where(Opportunity.stage == stage)
        ) or 0
    opportunities_won = db.scalar(
        select(func.count()).select_from(Opportunity).where(Opportunity.stage == OpportunityStage.WON)
    ) or 0
    opportunities_lost = db.scalar(
        select(func.count()).select_from(Opportunity).where(Opportunity.stage == OpportunityStage.LOST)
    ) or 0
    closed_total = opportunities_won + opportunities_lost
    opportunity_conversion_rate = (
        round(opportunities_won / closed_total * 100) if closed_total else None
    )

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
        "opportunities_suggested": opportunities_suggested,
        "opportunity_stage_counts": opportunity_stage_counts,
        "opportunities_won": opportunities_won,
        "opportunities_lost": opportunities_lost,
        "opportunity_conversion_rate": opportunity_conversion_rate,
    }


def _days_until_birthday(dob: date, today: date) -> int:
    """Days from today until the next occurrence of this birthday (0 = today)."""
    try:
        nxt = dob.replace(year=today.year)
    except ValueError:  # Feb 29 in a non-leap year
        nxt = date(today.year, 2, 28)
    if nxt < today:
        try:
            nxt = dob.replace(year=today.year + 1)
        except ValueError:
            nxt = date(today.year + 1, 2, 28)
    return (nxt - today).days


@router.get("/dashboard/overview")
def dashboard_overview(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """CRM-tailored roll-up: CSP (Kiosk Operator) network, the RMs who run it, call activity and
    upcoming birthdays - the figures this CRM actually runs on, shaped for an interactive dashboard."""
    active = CspStatus.ACTIVE

    active_csps = db.scalar(select(func.count()).select_from(Csp).where(Csp.status == active)) or 0
    rm_count = db.scalar(select(func.count()).select_from(User).where(User.role == Role.RELATIONSHIP_MANAGER)) or 0
    officials = db.scalar(
        select(func.count()).select_from(Official).where(Official.status == OfficialStatus.ACTIVE)
    ) or 0
    calls_total = db.scalar(select(func.count()).select_from(CallSession)) or 0
    recordings = db.scalar(select(func.count()).select_from(CallVoiceNote)) or 0

    csps_by_rm = [
        {"name": r[0], "value": r[1]}
        for r in db.execute(
            select(Csp.rm_name, func.count()).where(Csp.status == active)
            .group_by(Csp.rm_name).order_by(func.count().desc())
        ).all()
    ]
    csps_by_category = [
        {"name": r[0] or "Uncategorised", "value": r[1]}
        for r in db.execute(
            select(Csp.category, func.count()).where(Csp.status == active)
            .group_by(Csp.category).order_by(func.count().desc())
        ).all()
    ]
    csps_by_state = [
        {"name": r[0] or "Unknown", "value": r[1]}
        for r in db.execute(
            select(Csp.state, func.count()).where(Csp.status == active)
            .group_by(Csp.state).order_by(func.count().desc()).limit(8)
        ).all()
    ]

    calls_by_rm = [
        {"name": r[0], "value": r[1]}
        for r in db.execute(
            select(User.name, func.count()).join(CallSession, CallSession.dc_user_id == User.id)
            .where(User.role == Role.RELATIONSHIP_MANAGER)
            .group_by(User.name).order_by(func.count().desc())
        ).all()
    ]
    calls_by_direction = [
        {"name": (r[0] or "unknown").title(), "value": r[1]}
        for r in db.execute(
            select(CallSession.direction, func.count()).group_by(CallSession.direction)
        ).all()
    ]

    # Call activity over the last 14 days.
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=13)
    raw = db.execute(
        select(func.date(CallSession.started_at), func.count())
        .where(func.date(CallSession.started_at) >= start.isoformat())
        .group_by(func.date(CallSession.started_at))
    ).all()
    by_day = {str(r[0]): r[1] for r in raw}
    calls_timeline = [
        {"date": (start + timedelta(days=i)).isoformat(), "value": by_day.get((start + timedelta(days=i)).isoformat(), 0)}
        for i in range(14)
    ]

    # Upcoming CSP birthdays in the next 30 days.
    upcoming = []
    for c in db.scalars(
        select(Csp).where(Csp.status == active).where(Csp.date_of_birth.is_not(None))
    ).all():
        d = _days_until_birthday(c.date_of_birth, today)
        if d <= 30:
            upcoming.append({
                "csp_id": c.csp_id, "name": c.name, "rm_name": c.rm_name,
                "date": c.date_of_birth.replace(year=today.year).isoformat() if c.date_of_birth.month != 2 or c.date_of_birth.day != 29 else c.date_of_birth.isoformat(),
                "in_days": d, "email": c.email,
            })
    upcoming.sort(key=lambda x: x["in_days"])
    birthdays_7d = sum(1 for b in upcoming if b["in_days"] <= 7)

    return {
        "kpis": {
            "active_csps": active_csps,
            "relationship_managers": rm_count,
            "sbi_officials": officials,
            "calls_total": calls_total,
            "recordings": recordings,
            "birthdays_7d": birthdays_7d,
        },
        "csps_by_rm": csps_by_rm,
        "csps_by_category": csps_by_category,
        "csps_by_state": csps_by_state,
        "calls_by_rm": calls_by_rm,
        "calls_by_direction": calls_by_direction,
        "calls_timeline": calls_timeline,
        "upcoming_birthdays": upcoming[:12],
    }
