"""Engagement-moment detection, drafting, and the fatigue check.

Detection reads only *verified* dated facts. Nothing here sends anything;
the furthest a moment moves automatically is DETECTED (or a suppressed
DETECTED). A human drafts, approves, sends by hand, then records the outcome.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.engagement_moment import EngagementMoment, MomentStatus, MomentType
from ..models.interaction import Interaction
from ..models.official import FieldVerification
from ..models.official_date import DateKind, OfficialDate
from ..models.organization_unit import OrganizationUnit
from ..models.relationship import Relationship, RelationshipStatus
from ..services import audit
from ..services.scoring import band

settings = get_settings()

_ELIGIBLE_STATUSES = {
    RelationshipStatus.DEVELOPING,
    RelationshipStatus.ACTIVE,
    RelationshipStatus.STRONG,
    RelationshipStatus.STRATEGIC,
    RelationshipStatus.DECLINING,
}
_OPEN_STATUSES = (
    MomentStatus.DETECTED,
    MomentStatus.DRAFT_READY,
    MomentStatus.APPROVED,
)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_since_last_interaction(rel: Relationship, now: datetime) -> int | None:
    if rel.last_interaction_at is None:
        return None
    return (now - _aware(rel.last_interaction_at)).days


def _last_sentiment(db: Session, rel: Relationship) -> str | None:
    row = db.scalar(
        select(Interaction)
        .where(Interaction.relationship_id == rel.id)
        .order_by(Interaction.occurred_at.desc())
        .limit(1)
    )
    return row.sentiment.value if row else None


def _next_occurrence(anniversary: date, today: date) -> date:
    year = today.year
    try:
        candidate = anniversary.replace(year=year)
    except ValueError:  # 29 Feb
        candidate = anniversary.replace(year=year, day=28)
    if candidate < today:
        try:
            candidate = anniversary.replace(year=year + 1)
        except ValueError:
            candidate = anniversary.replace(year=year + 1, day=28)
    return candidate


def _verified_dates(db: Session, official_id: int, kind: DateKind) -> list[OfficialDate]:
    return list(
        db.scalars(
            select(OfficialDate)
            .where(OfficialDate.official_id == official_id)
            .where(OfficialDate.kind == kind)
            .where(OfficialDate.verification_status == FieldVerification.VERIFIED)
        )
    )


def _existing_open(
    db: Session, rel_id: int, moment_type: MomentType, event_date: date | None
) -> EngagementMoment | None:
    stmt = (
        select(EngagementMoment)
        .where(EngagementMoment.relationship_id == rel_id)
        .where(EngagementMoment.type == moment_type)
        .where(EngagementMoment.status.in_(_OPEN_STATUSES))
    )
    if event_date is not None:
        stmt = stmt.where(EngagementMoment.event_date == event_date)
    return db.scalar(stmt)


def fatigue_reason(db: Session, rel: Relationship, now: datetime) -> str | None:
    days = _days_since_last_interaction(rel, now)
    if days is not None and days < settings.moment_fatigue_days:
        return f"recent contact {days} day(s) ago"
    other = db.scalar(
        select(EngagementMoment)
        .where(EngagementMoment.relationship_id == rel.id)
        .where(EngagementMoment.status.in_(_OPEN_STATUSES))
    )
    if other is not None:
        return "another moment for this relationship is already open"
    return None


def _evidence(
    db: Session, rel: Relationship, now: datetime, *, trigger: str, source: str | None
) -> dict:
    days = _days_since_last_interaction(rel, now)
    label, _ = band(rel.score)
    return {
        "trigger": trigger,
        "source": source,
        "days_since_last_interaction": days,
        "last_sentiment": _last_sentiment(db, rel),
        "relationship_band": label,
        "relationship_status": rel.status.value,
        "importance": rel.importance.value,
        "score": rel.score,
    }


def _create(
    db: Session,
    rel: Relationship,
    moment_type: MomentType,
    event_date: date | None,
    evidence: dict,
    *,
    suppressed_reason: str | None,
) -> EngagementMoment:
    moment = EngagementMoment(
        official_id=rel.official_id,
        relationship_id=rel.id,
        type=moment_type,
        event_date=event_date,
        evidence=evidence,
        status=MomentStatus.DETECTED,
        suppressed_reason=suppressed_reason,
    )
    db.add(moment)
    db.flush()
    audit.record(
        db,
        action="moment.detected",
        entity_type="engagement_moment",
        entity_id=moment.id,
        after={
            "type": moment_type.value,
            "event_date": event_date.isoformat() if event_date else None,
            "suppressed": bool(suppressed_reason),
        },
    )
    return moment


def detect_for_relationship(
    db: Session, rel: Relationship, now: datetime | None = None
) -> list[EngagementMoment]:
    if not settings.enable_moments:
        return []
    if rel.status not in _ELIGIBLE_STATUSES:
        return []

    now = now or datetime.now(timezone.utc)
    today = now.date()
    lookahead = timedelta(days=settings.moment_lookahead_days)
    created: list[EngagementMoment] = []
    suppression = fatigue_reason(db, rel, now)

    # --- promotion: a verified promotion date in the recent window ---------
    for d in _verified_dates(db, rel.official_id, DateKind.PROMOTED):
        age = (today - d.value).days
        if 0 <= age <= settings.moment_promotion_recent_days:
            if _existing_open(db, rel.id, MomentType.PROMOTION, d.value):
                continue
            ev = _evidence(
                db, rel, now,
                trigger=f"verified promotion on {d.value.isoformat()}",
                source=d.source,
            )
            created.append(
                _create(db, rel, MomentType.PROMOTION, d.value, ev,
                        suppressed_reason=suppression)
            )

    # --- birthday: verified, next occurrence within the lookahead ---------
    for d in _verified_dates(db, rel.official_id, DateKind.BIRTHDAY):
        nxt = _next_occurrence(d.value, today)
        if today <= nxt <= today + lookahead:
            if _existing_open(db, rel.id, MomentType.BIRTHDAY, nxt):
                continue
            ev = _evidence(
                db, rel, now,
                trigger=f"birthday on {nxt.isoformat()}", source=d.source,
            )
            created.append(
                _create(db, rel, MomentType.BIRTHDAY, nxt, ev,
                        suppressed_reason=suppression)
            )

    # --- work anniversary: verified joining date, whole-year multiple -----
    for d in _verified_dates(db, rel.official_id, DateKind.JOINED):
        nxt = _next_occurrence(d.value, today)
        years = nxt.year - d.value.year
        if years >= 1 and today <= nxt <= today + lookahead:
            if _existing_open(db, rel.id, MomentType.WORK_ANNIVERSARY, nxt):
                continue
            ev = _evidence(
                db, rel, now,
                trigger=f"{years}-year work anniversary on {nxt.isoformat()}",
                source=d.source,
            )
            ev["years"] = years
            created.append(
                _create(db, rel, MomentType.WORK_ANNIVERSARY, nxt, ev,
                        suppressed_reason=suppression)
            )

    # --- inactivity: no contact for a long time on an active relationship -
    days = _days_since_last_interaction(rel, now)
    if (
        days is not None
        and days >= settings.moment_inactivity_days
        and rel.status in {
            RelationshipStatus.ACTIVE,
            RelationshipStatus.STRONG,
            RelationshipStatus.STRATEGIC,
        }
        and not _existing_open(db, rel.id, MomentType.INACTIVITY, None)
    ):
        ev = _evidence(
            db, rel, now,
            trigger=f"no interaction for {days} days", source="relationship activity",
        )
        # inactivity is never suppressed by fatigue - it *is* the fatigue signal
        created.append(
            _create(db, rel, MomentType.INACTIVITY, None, ev, suppressed_reason=None)
        )

    return created


def detect_all(db: Session, now: datetime | None = None) -> int:
    if not settings.enable_moments:
        return 0
    total = 0
    for rel in db.scalars(select(Relationship)).all():
        total += len(detect_for_relationship(db, rel, now))
    db.flush()
    return total


# --- drafting ----------------------------------------------------------------

def _unit_name(db: Session, official) -> str:
    if official.organization_unit_id:
        unit = db.get(OrganizationUnit, official.organization_unit_id)
        if unit:
            return unit.name
    return official.location or "their office"


def build_draft(db: Session, moment: EngagementMoment, sender_name: str | None) -> str:
    official = moment.official
    name = official.name
    sender = sender_name or "the team"
    designation = official.designation or "the new role"

    if moment.type is MomentType.PROMOTION:
        return (
            f"Dear {name},\n\nWarm congratulations on your elevation to "
            f"{designation}. We have valued working with you and wish you "
            f"continued success in this new responsibility.\n\nBest regards,\n{sender}"
        )
    if moment.type is MomentType.BIRTHDAY:
        return (
            f"Dear {name},\n\nWishing you a very happy birthday and a healthy, "
            f"successful year ahead.\n\nWarm regards,\n{sender}"
        )
    if moment.type is MomentType.WORK_ANNIVERSARY:
        years = moment.evidence.get("years", "")
        return (
            f"Dear {name},\n\nCongratulations on completing {years} years of "
            f"service. Thank you for your continued support.\n\n"
            f"Best regards,\n{sender}"
        )
    days = moment.evidence.get("days_since_last_interaction", "")
    return (
        f"Suggested check-in: it has been {days} days since the last contact with "
        f"{name} at {_unit_name(db, official)}. A brief, non-sales courtesy note or "
        f"call would help keep the relationship warm."
    )
