"""Opportunity pipeline: detection, stage progression, activities and outcomes.

Detection mirrors ``services/connections.py`` exactly: a manual entry lands
CONFIRMED; something the extractor pulled out of an interaction note lands
SUGGESTED and waits for a human to confirm or dismiss it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.interaction import Interaction
from ..models.opportunity import (
    Opportunity,
    OpportunityActivity,
    OpportunityActivityType,
    OpportunityStage,
    OpportunityStatus,
)
from ..models.relationship import Relationship

_CLOSED_STAGES = (OpportunityStage.WON, OpportunityStage.LOST)


def _field(interaction: Interaction, key: str) -> list:
    """Prefer the effective ``structured`` field, fall back to raw model output.
    Same helper as connections.py's _field."""
    val = (interaction.structured or {}).get(key)
    if not val:
        val = (interaction.ai_structured or {}).get(key)
    return list(val or [])


def _existing_open(db: Session, relationship_id: int, title: str) -> Opportunity | None:
    return db.scalar(
        select(Opportunity)
        .where(Opportunity.relationship_id == relationship_id)
        .where(func.lower(Opportunity.title) == title.lower())
        .where(Opportunity.status != OpportunityStatus.DISMISSED)
        .where(Opportunity.stage.not_in(_CLOSED_STAGES))
    )


def has_open_for_relationship(db: Session, relationship_id: int) -> bool:
    """Whether this relationship already has ANY opportunity in flight,
    regardless of title wording - used by the agent to avoid recommending a
    new one when one is already being tracked (title-exact dedup alone isn't
    enough there, since two independent extractions rarely phrase the same
    signal identically)."""
    return (
        db.scalar(
            select(Opportunity.id)
            .where(Opportunity.relationship_id == relationship_id)
            .where(Opportunity.status != OpportunityStatus.DISMISSED)
            .where(Opportunity.stage.not_in(_CLOSED_STAGES))
        )
        is not None
    )


def upsert(
    db: Session,
    *,
    relationship: Relationship,
    title: str,
    source: str,
    status: OpportunityStatus,
    detail: str | None = None,
    actor_id: int | None = None,
    source_interaction_id: int | None = None,
) -> tuple[Opportunity, bool]:
    """Create the opportunity, or return the existing open one for this title.
    Returns (opportunity, created).

    A CONFIRMED request always wins - it lifts a prior SUGGESTED or DISMISSED
    row (an RM re-asserting a fact overrides an earlier dismissal), same rule
    as connections.upsert.
    """
    existing = _existing_open(db, relationship.id, title)
    if existing is not None:
        if status is OpportunityStatus.CONFIRMED and existing.status is not OpportunityStatus.CONFIRMED:
            existing.status = OpportunityStatus.CONFIRMED
            existing.source = source
            existing.decided_by = actor_id
            existing.decided_at = datetime.now(timezone.utc)
        return existing, False

    opp = Opportunity(
        relationship_id=relationship.id,
        official_id=relationship.official_id,
        title=title,
        detail=detail,
        status=status,
        stage=OpportunityStage.IDENTIFIED,
        source=source,
        source_interaction_id=source_interaction_id,
        created_by=actor_id,
    )
    if status is OpportunityStatus.CONFIRMED:
        opp.decided_by = actor_id
        opp.decided_at = datetime.now(timezone.utc)
    db.add(opp)
    db.flush()
    return opp, True


def set_status(
    db: Session, opp: Opportunity, status: OpportunityStatus, *, actor_id: int
) -> Opportunity:
    opp.status = status
    opp.decided_by = actor_id
    opp.decided_at = datetime.now(timezone.utc)
    return opp


def change_stage(
    db: Session,
    opp: Opportunity,
    stage: OpportunityStage,
    *,
    actor_id: int | None,
    outcome_note: str | None = None,
) -> Opportunity:
    if opp.status is not OpportunityStatus.CONFIRMED:
        raise ValueError("Confirm the opportunity before moving it through the pipeline")

    from_stage = opp.stage
    opp.stage = stage
    if stage in _CLOSED_STAGES:
        opp.closed_at = datetime.now(timezone.utc)
        opp.outcome_note = outcome_note

    db.add(
        OpportunityActivity(
            opportunity_id=opp.id,
            type=OpportunityActivityType.STAGE_CHANGE,
            occurred_at=datetime.now(timezone.utc),
            note=f"Stage changed from {from_stage.value} to {stage.value}.",
            from_stage=from_stage,
            to_stage=stage,
            created_by=actor_id,
        )
    )
    db.flush()
    return opp


def log_activity(
    db: Session,
    opp: Opportunity,
    *,
    type_: OpportunityActivityType,
    note: str,
    occurred_at: datetime | None = None,
    actor_id: int | None = None,
) -> OpportunityActivity:
    if type_ is OpportunityActivityType.STAGE_CHANGE:
        raise ValueError("stage_change activities are system-logged only")
    if opp.status is not OpportunityStatus.CONFIRMED:
        raise ValueError("Confirm the opportunity before logging activity against it")

    activity = OpportunityActivity(
        opportunity_id=opp.id,
        type=type_,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        note=note,
        created_by=actor_id,
    )
    db.add(activity)
    db.flush()
    return activity


def suggest_from_interaction(db: Session, interaction: Interaction) -> int:
    """Propose opportunities from what the extractor pulled out of one
    interaction's notes. Only landed as SUGGESTED - a human confirms or
    dismisses each one. Returns the number of new suggestions."""
    rel = db.get(Relationship, interaction.relationship_id)
    if rel is None:
        return 0

    created = 0
    for text in _field(interaction, "opportunities"):
        title = str(text).strip()[:300]
        if not title:
            continue
        _, was_new = upsert(
            db,
            relationship=rel,
            title=title,
            source=f"Extracted from interaction #{interaction.id}",
            status=OpportunityStatus.SUGGESTED,
            source_interaction_id=interaction.id,
        )
        created += int(was_new)
    return created
