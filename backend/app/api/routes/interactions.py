"""Interactions: logging contact, AI extraction, and re-processing."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.interaction import Interaction, InteractionType
from ...models.official import Official
from ...models.relationship import Relationship
from ...models.user import Role, User
from ...schemas.interaction import (
    EmailParseRequest,
    InteractionCreate,
    InteractionDetail,
    InteractionListResponse,
    InteractionSummary,
    InteractionUpdate,
    ParsedEmailOut,
)
from ...security.deps import get_current_user, require_roles
from ...services import audit, scoring
from ...services import connections as connections_svc
from ...services.importance import recompute as recompute_importance
from ...services.email_parse import parse_email
from ...services.llm import extract_interaction

router = APIRouter(prefix="/interactions", tags=["interactions"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)


def _apply_extraction(interaction: Interaction) -> None:
    result = extract_interaction(
        interaction.raw_notes, interaction_type=interaction.type.value
    )
    payload = {
        "topics": result.topics,
        "commitments": result.commitments,
        "requests": result.requests,
        "people": result.people,
    }
    interaction.ai_summary = result.summary
    interaction.ai_structured = payload
    interaction.ai_model = result.model
    interaction.sentiment = result.sentiment
    interaction.structured = payload


@router.post("/email/parse", response_model=ParsedEmailOut)
def parse_email_endpoint(
    payload: EmailParseRequest,
    db: Session = Depends(get_db),
    _: User = Depends(_EDITORS),
):
    """Parse a pasted email / .eml body. Read-only — nothing is saved."""
    parsed = parse_email(payload.raw_email)

    matched_official_id = matched_official_name = matched_relationship_id = None
    if parsed.from_email:
        official = db.scalar(
            select(Official).where(func.lower(Official.email) == parsed.from_email)
        )
        if official is not None:
            matched_official_id = official.id
            matched_official_name = official.name
            rel = db.scalar(
                select(Relationship).where(Relationship.official_id == official.id)
            )
            matched_relationship_id = rel.id if rel else None

    return ParsedEmailOut(
        from_name=parsed.from_name,
        from_email=parsed.from_email,
        to=parsed.to,
        date=parsed.date,
        subject=parsed.subject,
        body=parsed.body,
        quoted_removed=parsed.quoted_removed,
        matched_official_id=matched_official_id,
        matched_official_name=matched_official_name,
        matched_relationship_id=matched_relationship_id,
    )


@router.get("", response_model=InteractionListResponse)
def list_interactions(
    relationship_id: int | None = None,
    official_id: int | None = None,
    type_filter: InteractionType | None = Query(default=None, alias="type"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    filters = []
    if relationship_id is not None:
        filters.append(Interaction.relationship_id == relationship_id)
    if official_id is not None:
        filters.append(Interaction.official_id == official_id)
    if type_filter is not None:
        filters.append(Interaction.type == type_filter)

    total = db.scalar(
        select(func.count()).select_from(Interaction).where(*filters)
    ) or 0
    rows = db.scalars(
        select(Interaction)
        .where(*filters)
        .order_by(Interaction.occurred_at.desc(), Interaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return InteractionListResponse(
        items=[InteractionSummary.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=InteractionDetail, status_code=status.HTTP_201_CREATED)
def create_interaction(
    payload: InteractionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rel = db.get(Relationship, payload.relationship_id)
    if rel is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Relationship not found")

    interaction = Interaction(
        relationship_id=rel.id,
        official_id=rel.official_id,
        type=payload.type,
        direction=payload.direction,
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
        channel=payload.channel,
        raw_notes=payload.raw_notes,
        created_by=actor.id,
    )
    _apply_extraction(interaction)
    db.add(interaction)
    db.flush()

    # names co-mentioned here -> suggested "works_with" edges for a human to confirm
    connections_svc.suggest_from_interaction(db, interaction)

    recompute_importance(db, rel)
    scoring.recompute_and_store(db, rel, reason="interaction logged")
    audit.record(
        db,
        action="interaction.create",
        entity_type="interaction",
        entity_id=interaction.id,
        actor_id=actor.id,
        after={
            "relationship_id": rel.id,
            "type": interaction.type.value,
            "sentiment": interaction.sentiment.value,
            "ai_model": interaction.ai_model,
        },
    )
    db.commit()
    db.refresh(interaction)
    return InteractionDetail.model_validate(interaction)


@router.get("/{interaction_id}", response_model=InteractionDetail)
def get_interaction(
    interaction_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    interaction = db.get(Interaction, interaction_id)
    if interaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interaction not found")
    return InteractionDetail.model_validate(interaction)


@router.patch("/{interaction_id}", response_model=InteractionDetail)
def update_interaction(
    interaction_id: int,
    payload: InteractionUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    interaction = db.get(Interaction, interaction_id)
    if interaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interaction not found")

    data = payload.model_dump(exclude_unset=True)
    rescore = False
    for key in ("type", "direction", "occurred_at", "channel", "raw_notes", "structured", "sentiment"):
        if key in data:
            setattr(interaction, key, data[key])
            if key in ("type", "occurred_at"):
                rescore = True

    db.flush()
    if rescore or "sentiment" in data:
        recompute_importance(db, interaction.relationship_ref)
    if rescore:
        scoring.recompute_and_store(
            db, interaction.relationship_ref, reason="interaction edited"
        )
    audit.record(
        db,
        action="interaction.update",
        entity_type="interaction",
        entity_id=interaction.id,
        actor_id=actor.id,
        after={k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in data.items() if k != "structured"},
    )
    db.commit()
    db.refresh(interaction)
    return InteractionDetail.model_validate(interaction)


@router.post("/{interaction_id}/reprocess", response_model=InteractionDetail)
def reprocess_interaction(
    interaction_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    interaction = db.get(Interaction, interaction_id)
    if interaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interaction not found")

    result = extract_interaction(
        interaction.raw_notes, interaction_type=interaction.type.value
    )
    # Reprocess replaces the model's output only; the effective (human-edited)
    # structured data and sentiment are left as-is.
    interaction.ai_summary = result.summary
    interaction.ai_structured = {
        "topics": result.topics,
        "commitments": result.commitments,
        "requests": result.requests,
        "people": result.people,
    }
    interaction.ai_model = result.model

    audit.record(
        db,
        action="interaction.reprocess",
        entity_type="interaction",
        entity_id=interaction.id,
        actor_id=actor.id,
        after={"ai_model": interaction.ai_model},
    )
    db.commit()
    db.refresh(interaction)
    return InteractionDetail.model_validate(interaction)
