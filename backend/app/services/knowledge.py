"""RAG: chunking, indexing, and similarity search over existing text fields.

No new "document" concept - chunks point at text that already lives on an
Interaction/EngagementMoment/Opportunity row. Search is always scoped to a
caller-supplied set of relationship ids (never an unbounded table scan) and
never raises - RAG is a context-quality improvement, not a hard dependency
for /ask or the Brief to keep working.
"""

from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.knowledge import KnowledgeChunk
from . import embeddings

settings = get_settings()

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, *, max_chars: int = 600) -> list[str]:
    """Deterministic sentence-packing chunker - no ML tokenizer needed for
    short CRM notes. Packs whole sentences into ~max_chars chunks; a single
    sentence longer than max_chars becomes its own (oversized) chunk rather
    than being cut mid-word.
    """
    text = (text or "").strip()
    if not text:
        return []
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def index_source(
    db: Session,
    source_type: str,
    source_id: int,
    text: str | None,
    *,
    relationship_id: int,
    official_id: int,
) -> None:
    """Replace all chunks for this (source_type, source_id) wholesale - the
    same "replaced wholesale on reprocess" idiom already used for
    Interaction.ai_structured. Never raises: indexing failure must not block
    saving the interaction/moment/opportunity it's derived from.
    """
    try:
        db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.source_type == source_type,
                KnowledgeChunk.source_id == source_id,
            )
        )
        if not settings.enable_rag:
            return
        for i, piece in enumerate(chunk_text(text or "")):
            vector = embeddings.embed(piece)
            db.add(
                KnowledgeChunk(
                    source_type=source_type,
                    source_id=source_id,
                    relationship_id=relationship_id,
                    official_id=official_id,
                    chunk_index=i,
                    text=piece,
                    embedding=vector,
                    embedding_model=settings.embedding_model,
                )
            )
        db.flush()
    except Exception:
        pass


def reindex_all(db: Session) -> int:
    """Manual, on-demand full reindex - e.g. after enabling RAG on an
    existing database or changing the embedding model. Not a background
    worker; an admin triggers this explicitly.
    """
    from ..models.engagement_moment import EngagementMoment
    from ..models.interaction import Interaction
    from ..models.opportunity import Opportunity

    count = 0
    for interaction in db.scalars(select(Interaction)).all():
        index_source(
            db,
            "interaction",
            interaction.id,
            interaction.raw_notes,
            relationship_id=interaction.relationship_id,
            official_id=interaction.official_id,
        )
        count += 1
    for moment in db.scalars(select(EngagementMoment).where(EngagementMoment.draft_text.is_not(None))).all():
        index_source(
            db,
            "moment_draft",
            moment.id,
            moment.draft_text,
            relationship_id=moment.relationship_id,
            official_id=moment.official_id,
        )
        count += 1
    for opp in db.scalars(select(Opportunity).where(Opportunity.detail.is_not(None))).all():
        index_source(
            db,
            "opportunity_detail",
            opp.id,
            opp.detail,
            relationship_id=opp.relationship_id,
            official_id=opp.official_id,
        )
        count += 1
    db.flush()
    return count


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search(
    db: Session,
    *,
    relationship_ids: list[int],
    query: str,
    top_k: int | None = None,
) -> list[dict]:
    """Top-k chunks (by cosine similarity) among the given relationships only
    - the caller (supervisor/brief) has already resolved which relationships
    the question is allowed to touch; this never widens that scope. Returns
    [] whenever RAG is disabled, nothing is indexed, or nothing clears
    rag_min_similarity - callers must keep working via their existing
    template fallback in that case.
    """
    if not settings.enable_rag or not relationship_ids:
        return []
    query_vector = embeddings.embed(query)
    if query_vector is None:
        return []
    top_k = top_k or settings.rag_top_k

    rows = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.relationship_id.in_(relationship_ids))
        .where(KnowledgeChunk.embedding.is_not(None))
        .where(KnowledgeChunk.embedding_model == settings.embedding_model)
    ).all()

    scored = []
    for row in rows:
        score = cosine_similarity(query_vector, row.embedding or [])
        if score >= settings.rag_min_similarity:
            scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = []
    for score, row in scored[:top_k]:
        confidence = "high" if score >= 0.5 else "medium" if score >= 0.3 else "low"
        results.append(
            {
                "relationship_id": row.relationship_id,
                "official_id": row.official_id,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "text": row.text,
                "score": round(score, 4),
                "confidence": confidence,
            }
        )
    return results
