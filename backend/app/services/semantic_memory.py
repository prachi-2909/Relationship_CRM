"""Semantic memory: durable facts about an official, with conflict-aware
upsert so a verified fact never silently loses to a lower-trust one.

Extraction never invents facts offline - the deterministic stub returns []
rather than a shaky heuristic guess, matching the agent's own "an empty list
is a valid and often correct answer" philosophy (see agent.py's
_RECOMMEND_SYSTEM).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from ..config import get_settings
from ..models.official import PROVENANCED_FIELDS
from ..models.semantic_memory import SemanticMemoryFact, SemanticVerificationState
from ..models.user import User
from . import audit, llm

settings = get_settings()

_EXTRACT_SYSTEM = (
    "You extract durable, factual statements about a person from one CRM "
    "interaction note - things worth remembering long-term (a stated "
    "preference, a role or responsibility not already obvious, a recurring "
    "pattern, a goal they mentioned). Do NOT extract routine chit-chat, "
    "one-off scheduling details, or anything not clearly stated in the "
    "text. An empty list is a valid and often correct answer - only extract "
    "what the text clearly supports.\n\n"
    'Reply with ONLY a JSON object: {"facts": [{"fact_text": a short plain '
    'sentence, "fact_key": a short lowercase_snake_case topic slug (e.g. '
    '"preferred_channel", "reports_to_note"), "confidence": integer 0-100}]}.'
)


class ExtractedFact(BaseModel):
    fact_text: str
    fact_key: str | None = None
    confidence: int = 50


class _ExtractionSet(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)


def extract_facts(text: str) -> list[ExtractedFact]:
    text = (text or "").strip()
    if not text or not settings.enable_semantic_memory:
        return []
    if not settings.llm_base_url:
        return []
    try:
        raw = llm.chat(_EXTRACT_SYSTEM, text)
        if not raw:
            return []
        data = _ExtractionSet.model_validate_json(llm._json_blob(raw))
        return data.facts
    except Exception:
        return []


def _existing_fact(db: Session, official_id: int, fact_key: str) -> SemanticMemoryFact | None:
    return db.scalar(
        select(SemanticMemoryFact)
        .where(SemanticMemoryFact.official_id == official_id)
        .where(SemanticMemoryFact.fact_key == fact_key)
        .where(SemanticMemoryFact.verification_state != SemanticVerificationState.SUPERSEDED)
        .order_by(SemanticMemoryFact.created_at.desc())
    )


def upsert_fact(
    db: Session,
    *,
    official_id: int,
    fact_text: str,
    relationship_id: int | None = None,
    fact_key: str | None = None,
    confidence: int | None = None,
    source_type: str = "interaction",
    source_interaction_id: int | None = None,
    created_by: int | None = None,
) -> SemanticMemoryFact | None:
    """Create, or resolve a conflict with, a fact for this official.

    Returns None when a lower-trust write is correctly dropped in favor of
    an existing, more-trusted fact (the conflict is still audited).
    """
    if fact_key and fact_key in PROVENANCED_FIELDS:
        # already owned by OfficialFieldProvenance's closed schema - not this table's job
        return None

    is_human_edit = source_type == "human_edit"
    verification = (
        SemanticVerificationState.HUMAN_CONFIRMED if is_human_edit else SemanticVerificationState.UNVERIFIED
    )

    existing = _existing_fact(db, official_id, fact_key) if fact_key else None
    if existing is not None:
        if existing.verification_state == SemanticVerificationState.HUMAN_CONFIRMED and not is_human_edit:
            audit.record(
                db,
                action="semantic_memory.fact.conflict_ignored",
                entity_type="semantic_memory_fact",
                entity_id=existing.id,
                actor_id=created_by,
                after={"attempted_fact_text": fact_text, "attempted_confidence": confidence},
            )
            return None
        if existing.verification_state == SemanticVerificationState.UNVERIFIED and not is_human_edit:
            if (confidence or 0) < (existing.confidence or 0):
                return None
        # either existing is unverified and this write is confident enough,
        # or this is a human edit superseding a prior (possibly confirmed) fact
        existing.verification_state = SemanticVerificationState.SUPERSEDED

    fact = SemanticMemoryFact(
        official_id=official_id,
        relationship_id=relationship_id,
        fact_text=fact_text,
        fact_key=fact_key,
        confidence=confidence,
        verification_state=verification,
        source_type=source_type,
        source_interaction_id=source_interaction_id,
        created_by=created_by,
    )
    db.add(fact)
    db.flush()
    if existing is not None:
        existing.superseded_by_id = fact.id
    audit.record(
        db,
        action="semantic_memory.fact.created",
        entity_type="semantic_memory_fact",
        entity_id=fact.id,
        actor_id=created_by,
        after={"fact_text": fact_text, "fact_key": fact_key, "source_type": source_type},
    )
    return fact


def verify_fact(db: Session, fact: SemanticMemoryFact, actor: User) -> SemanticMemoryFact:
    fact.verification_state = SemanticVerificationState.HUMAN_CONFIRMED
    audit.record(
        db,
        action="semantic_memory.fact.verified",
        entity_type="semantic_memory_fact",
        entity_id=fact.id,
        actor_id=actor.id,
    )
    return fact


def reject_fact(db: Session, fact: SemanticMemoryFact, actor: User, reason: str | None = None) -> SemanticMemoryFact:
    fact.verification_state = SemanticVerificationState.HUMAN_REJECTED
    audit.record(
        db,
        action="semantic_memory.fact.rejected",
        entity_type="semantic_memory_fact",
        entity_id=fact.id,
        actor_id=actor.id,
        after={"reason": reason} if reason else None,
    )
    return fact


def facts_for_official(db: Session, official_id: int, *, limit: int = 5) -> list[SemanticMemoryFact]:
    return list(
        db.scalars(
            select(SemanticMemoryFact)
            .where(SemanticMemoryFact.official_id == official_id)
            .where(SemanticMemoryFact.verification_state != SemanticVerificationState.SUPERSEDED)
            .where(SemanticMemoryFact.verification_state != SemanticVerificationState.HUMAN_REJECTED)
            .order_by(
                SemanticMemoryFact.verification_state == SemanticVerificationState.HUMAN_CONFIRMED,
                SemanticMemoryFact.confidence.desc().nulls_last(),
                SemanticMemoryFact.created_at.desc(),
            )
            .limit(limit)
        )
    )


def extract_and_store(
    db: Session,
    *,
    official_id: int,
    relationship_id: int,
    text: str,
    source_interaction_id: int | None = None,
) -> int:
    """Trigger-point helper: extract facts from one interaction's text and
    upsert each. Never raises - a bad extraction must not block saving the
    interaction it came from."""
    try:
        facts = extract_facts(text)
        count = 0
        for f in facts:
            if upsert_fact(
                db,
                official_id=official_id,
                relationship_id=relationship_id,
                fact_text=f.fact_text,
                fact_key=f.fact_key,
                confidence=f.confidence,
                source_type="interaction",
                source_interaction_id=source_interaction_id,
            ):
                count += 1
        return count
    except Exception:
        return 0
