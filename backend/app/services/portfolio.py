"""A lean, ranked scan across relationships — the Supervisor's other eye.

Deliberately NOT a loop of ``brief.build()`` calls: a full brief pulls
interactions, commitments, dated facts and more per relationship, which is
fine for one relationship but would be O(n) heavy queries across a whole
portfolio. This does the opposite: one query for the relationships (with
their official joined in already) plus two GROUP BY aggregates for open
moments and overdue follow-ups, merged in Python. Three queries total, no
matter how many relationships are in view.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.engagement_moment import EngagementMoment, MomentStatus
from ..models.relationship import Relationship
from ..models.task import Task, TaskStatus
from ..models.user import Role, User
from .scoring import band

_OPEN_MOMENT_STATUSES = (
    MomentStatus.DETECTED,
    MomentStatus.DRAFT_READY,
    MomentStatus.APPROVED,
)
_BAND_ORDER = {"At risk": 0, "Attention required": 1, "Healthy": 2, "Strong": 3}


def scan(db: Session, actor: User, *, limit: int = 20) -> list[dict]:
    """Compact, ranked view of the relationships ``actor`` can see.

    Ordered worst-first (band, then score) so "what needs attention" is
    always at the top. A relationship manager sees their own book; admin
    and approver-viewer see everything, matching the existing list rules.
    """
    filters = []
    if actor.role is Role.RELATIONSHIP_MANAGER:
        filters.append(Relationship.owner_id == actor.id)

    rels = db.scalars(select(Relationship).where(*filters)).all()
    if not rels:
        return []
    rel_ids = [r.id for r in rels]

    moment_counts = dict(
        db.execute(
            select(EngagementMoment.relationship_id, func.count())
            .where(EngagementMoment.relationship_id.in_(rel_ids))
            .where(EngagementMoment.status.in_(_OPEN_MOMENT_STATUSES))
            .group_by(EngagementMoment.relationship_id)
        ).all()
    )
    now = datetime.now(timezone.utc)
    overdue_counts = dict(
        db.execute(
            select(Task.relationship_id, func.count())
            .where(Task.relationship_id.in_(rel_ids))
            .where(Task.status == TaskStatus.OPEN)
            .where(Task.due_at.is_not(None))
            .where(Task.due_at < now)
            .group_by(Task.relationship_id)
        ).all()
    )

    rows = []
    for rel in rels:
        label, _ = band(rel.score)
        last = rel.last_interaction_at
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        rows.append(
            {
                "relationship_id": rel.id,
                "official_id": rel.official_id,
                "official_name": rel.official.name,
                "official_level": rel.official.level,
                "importance": rel.importance.value,
                "status": rel.status.value,
                "score": rel.score,
                "band": label,
                "days_since_last_contact": (now - last).days if last else None,
                "open_moments": moment_counts.get(rel.id, 0),
                "overdue_followups": overdue_counts.get(rel.id, 0),
            }
        )

    rows.sort(key=lambda r: (_BAND_ORDER.get(r["band"], 9), r["score"]))
    return rows[:limit]
