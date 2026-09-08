"""Relationship health score.

A transparent weighted average of signals, each 0-100. Signals that cannot be
computed yet (e.g. follow-up completion before tasks exist in 1D) return None
and their weight is redistributed across the rest. Every stored score records
the component values and the weight version that produced it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.interaction import Direction, Interaction, InteractionType
from ..models.relationship import (
    Relationship,
    RelationshipScoreHistory,
    RiskLevel,
)
from ..models.task import Task, TaskStatus

WEIGHTS_VERSION = "v1-2026-09"
WEIGHTS: dict[str, float] = {
    "recency": 25.0,
    "frequency": 25.0,
    "response": 20.0,
    "meeting": 15.0,
    "followup": 15.0,
}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _recency(db: Session, rel: Relationship, now: datetime) -> float | None:
    if rel.last_interaction_at is None:
        return 0.0
    days = (now - _aware(rel.last_interaction_at)).days
    return max(0.0, 100.0 - (days / 90.0) * 100.0)


def _count(db: Session, rel: Relationship, since: datetime, *, meeting_only: bool = False) -> int:
    stmt = (
        select(func.count())
        .select_from(Interaction)
        .where(Interaction.relationship_id == rel.id)
        .where(Interaction.occurred_at >= since)
    )
    if meeting_only:
        stmt = stmt.where(Interaction.type == InteractionType.MEETING)
    return db.scalar(stmt) or 0


def _frequency(db: Session, rel: Relationship, now: datetime) -> float | None:
    n = _count(db, rel, now - timedelta(days=90))
    return min(100.0, n / 6.0 * 100.0)


def _response(db: Session, rel: Relationship, now: datetime) -> float | None:
    rows = db.scalars(
        select(Interaction.direction)
        .where(Interaction.relationship_id == rel.id)
        .where(Interaction.occurred_at >= now - timedelta(days=90))
    ).all()
    if not rows:
        return 0.0
    inbound = sum(1 for d in rows if d == Direction.INBOUND)
    return inbound / len(rows) * 100.0


def _meeting(db: Session, rel: Relationship, now: datetime) -> float | None:
    n = _count(db, rel, now - timedelta(days=180), meeting_only=True)
    return min(100.0, n / 3.0 * 100.0)


def _followup(db: Session, rel: Relationship, now: datetime) -> float | None:
    since = now - timedelta(days=90)
    total = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.relationship_id == rel.id)
        .where(Task.status != TaskStatus.CANCELLED)
        .where(Task.created_at >= since)
    ) or 0
    if total == 0:
        return None  # no follow-ups yet -> weight is redistributed
    done = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.relationship_id == rel.id)
        .where(Task.status == TaskStatus.DONE)
        .where(Task.created_at >= since)
    ) or 0
    return done / total * 100.0


_SIGNALS = {
    "recency": _recency,
    "frequency": _frequency,
    "response": _response,
    "meeting": _meeting,
    "followup": _followup,
}


def band(score: int) -> tuple[str, RiskLevel]:
    if score >= 80:
        return "Strong", RiskLevel.LOW
    if score >= 60:
        return "Healthy", RiskLevel.LOW
    if score >= 40:
        return "Attention required", RiskLevel.MEDIUM
    return "At risk", RiskLevel.HIGH


def compute_score(db: Session, rel: Relationship) -> tuple[int, dict]:
    now = datetime.now(timezone.utc)
    raw = {name: fn(db, rel, now) for name, fn in _SIGNALS.items()}
    active = {k: v for k, v in raw.items() if v is not None}

    weight_sum = sum(WEIGHTS[k] for k in active)
    score = (
        round(sum(v * WEIGHTS[k] for k, v in active.items()) / weight_sum)
        if weight_sum
        else 0
    )
    components = {k: round(v, 1) for k, v in active.items()}
    components["_weights"] = {k: WEIGHTS[k] for k in active}
    components["_version"] = WEIGHTS_VERSION
    return score, components


def refresh_last_interaction(db: Session, rel: Relationship) -> None:
    latest = db.scalar(
        select(func.max(Interaction.occurred_at)).where(
            Interaction.relationship_id == rel.id
        )
    )
    rel.last_interaction_at = latest


def recompute_and_store(
    db: Session, rel: Relationship, *, reason: str
) -> RelationshipScoreHistory:
    refresh_last_interaction(db, rel)
    score, components = compute_score(db, rel)
    _, risk = band(score)
    rel.score = score
    rel.risk_level = risk

    entry = RelationshipScoreHistory(
        relationship_id=rel.id,
        score=score,
        components=components,
        weights_version=WEIGHTS_VERSION,
        reason=reason,
        computed_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry
