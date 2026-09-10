"""Relationship importance — derived, not set by hand.

Base tier comes from the official's level (seniority). Sustained positive
engagement bumps it up one tier; negative engagement never lowers it (a
souring senior relationship is still important — it needs attention).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.interaction import Interaction, Sentiment
from ..models.official import Official
from ..models.relationship import Importance, Relationship

# tier 3 (strategic) / tier 2 (important) level markers
_STRATEGIC_TOKENS = {
    "cgm", "dgm", "gm", "md", "ceo", "coo", "cfo", "cto", "director",
    "president", "chairman",
}
_STRATEGIC_PHRASES = (
    "managing director", "chief general manager", "deputy general manager",
    "chief executive", "head of",
)
_IMPORTANT_TOKENS = {"agm", "vp", "svp", "avp", "dvp"}
_IMPORTANT_PHRASES = (
    "assistant general manager", "regional manager", "chief manager",
    "vice president", "operation head", "operations head", "branch head",
    "team lead", "manager",
)

_SENTIMENT_WINDOW_DAYS = 180
_TIER_TO_IMPORTANCE = {
    1: Importance.ROUTINE,
    2: Importance.IMPORTANT,
    3: Importance.STRATEGIC,
}


def _level_tier(official: Official) -> int:
    text = (official.level or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    if tokens & _STRATEGIC_TOKENS or any(p in text for p in _STRATEGIC_PHRASES):
        return 3
    if tokens & _IMPORTANT_TOKENS or any(p in text for p in _IMPORTANT_PHRASES):
        return 2
    return 1


def _sentiment_bump(db: Session, rel: Relationship) -> tuple[int, dict]:
    since = datetime.now(timezone.utc) - timedelta(days=_SENTIMENT_WINDOW_DAYS)
    rows = db.scalars(
        select(Interaction.sentiment)
        .where(Interaction.relationship_id == rel.id)
        .where(Interaction.occurred_at >= since)
        .where(Interaction.sentiment.in_([Sentiment.POSITIVE, Sentiment.NEGATIVE]))
    ).all()
    pos = sum(1 for s in rows if s is Sentiment.POSITIVE)
    neg = sum(1 for s in rows if s is Sentiment.NEGATIVE)
    n = len(rows)
    lean = (pos - neg) / n if n else 0.0
    bump = 1 if n >= 2 and lean >= 0.34 else 0
    return bump, {"positive": pos, "negative": neg, "lean": round(lean, 2), "bump": bump}


def compute(db: Session, rel: Relationship) -> tuple[Importance, dict]:
    base_tier = _level_tier(rel.official)
    bump, sent = _sentiment_bump(db, rel)
    tier = min(3, base_tier + bump)
    reasons = {
        "level": rel.official.level,
        "base_tier": base_tier,
        "sentiment": sent,
        "result_tier": tier,
    }
    return _TIER_TO_IMPORTANCE[tier], reasons


def recompute(db: Session, rel: Relationship) -> Importance:
    value, _ = compute(db, rel)
    rel.importance = value
    return value
