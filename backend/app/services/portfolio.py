"""A lean, ranked scan across relationships — the Supervisor's other eye.

Deliberately NOT a loop of ``brief.build()`` calls: a full brief pulls
interactions, commitments, dated facts and more per relationship, which is
fine for one relationship but would be O(n) heavy queries across a whole
portfolio. This does the opposite: one query for the relationships (with
their official joined in already), one query for open moments, and one for
overdue follow-ups - each row-level (not just a count) so the Supervisor can
say WHAT is open, not just how many - grouped by relationship in Python.
Three queries total, no matter how many relationships are in view.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
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

    moments_by_rel: dict[int, list[dict]] = {}
    for rel_id, mtype, mstatus in db.execute(
        select(
            EngagementMoment.relationship_id,
            EngagementMoment.type,
            EngagementMoment.status,
        )
        .where(EngagementMoment.relationship_id.in_(rel_ids))
        .where(EngagementMoment.status.in_(_OPEN_MOMENT_STATUSES))
    ):
        moments_by_rel.setdefault(rel_id, []).append(
            {"type": mtype.value, "status": mstatus.value}
        )

    now = datetime.now(timezone.utc)
    overdue_by_rel: dict[int, list[dict]] = {}
    for rel_id, title, due_at in db.execute(
        select(Task.relationship_id, Task.title, Task.due_at)
        .where(Task.relationship_id.in_(rel_ids))
        .where(Task.status == TaskStatus.OPEN)
        .where(Task.due_at.is_not(None))
        .where(Task.due_at < now)
    ):
        overdue_by_rel.setdefault(rel_id, []).append(
            {"title": title, "due_at": due_at.isoformat()}
        )

    rows = []
    for rel in rels:
        label, _ = band(rel.score)
        last = rel.last_interaction_at
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        moments = moments_by_rel.get(rel.id, [])
        overdue = overdue_by_rel.get(rel.id, [])
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
                "open_moments": len(moments),
                "moments": moments,
                "moment_draft_ready": any(
                    m["status"] in ("draft_ready", "approved") for m in moments
                ),
                "overdue_followups": len(overdue),
                "overdue_tasks": overdue,
            }
        )

    rows.sort(key=lambda r: (_BAND_ORDER.get(r["band"], 9), r["score"]))
    return rows[:limit]
