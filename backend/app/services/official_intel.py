"""Relationship intelligence for an SBI official - the DC-facing counterpart of the CSP pre-call briefing.

This is NOT a separate store. Everything is read from what the CRM already keeps: the official's
Interactions (the logged calls and meetings), the relationship, the semantic memory facts, the open
follow-up Tasks, the official's dates and opportunities - plus the shared Commitment table, where this
stream is tagged source_kind=dc_official.

A DC's call audio is discarded when the interaction is logged (a separate, unchanged flow). Nothing here
reads audio, transcripts or call-session rows, so the briefing is exactly as complete the day after
the audio is gone as the day it was logged.

Commitments of this stream become active only through a human: the DC confirms the (editable) brief and
that is the approval. Nothing extracted from an unconfirmed call is visible here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.commitment import CommitmentParty
from ..models.interaction import Interaction, Sentiment
from ..models.intelligence_feedback import SUBJECT_OFFICIAL, TARGET_FOLLOWUP, TARGET_TALKING_POINT
from ..models.official import Official
from ..models.official_date import DateKind, OfficialDate
from ..models.opportunity import Opportunity, OpportunityActivity, OpportunityStage, OpportunityStatus
from ..models.organization_unit import OrganizationUnit
from ..models.relationship import Relationship
from ..models.task import Task, TaskStatus
from ..models.user import User
from . import commitments as commitments_svc
from . import intelligence_feedback as feedback_svc
from . import semantic_memory as semantic_memory_svc
from .scoring import band

settings = get_settings()

MAX_ITEMS = 10
UPCOMING_DAYS = 14
STALE_OPPORTUNITY_DAYS = 30
_DATE_LABEL = {DateKind.BIRTHDAY: "birthday", DateKind.JOINED: "work anniversary",
               DateKind.MARRIAGE_ANNIVERSARY: "marriage anniversary"}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _next_occurrence(d: date, today: date) -> date:
    def on(year: int) -> date:
        try:
            return d.replace(year=year)
        except ValueError:  # 29 Feb in a non-leap year
            return d.replace(year=year, day=28)

    nxt = on(today.year)
    return nxt if nxt >= today else on(today.year + 1)


def _gather(db: Session, official: Official, now: datetime) -> dict:
    rel = db.scalar(select(Relationship).where(Relationship.official_id == official.id))
    interactions = db.scalars(
        select(Interaction).where(Interaction.official_id == official.id)
        .order_by(Interaction.occurred_at.desc()).limit(8)
    ).all()
    open_cs = commitments_svc.list_for_official(db, official.id)
    tasks = db.scalars(
        select(Task).where(Task.official_id == official.id).where(Task.status == TaskStatus.OPEN)
        .order_by(Task.due_at.is_(None), Task.due_at)
    ).all()
    upcoming = []
    for d in db.scalars(select(OfficialDate).where(OfficialDate.official_id == official.id)).all():
        if d.kind not in _DATE_LABEL:
            continue
        in_days = (_next_occurrence(d.value, now.date()) - now.date()).days
        if 0 <= in_days <= UPCOMING_DAYS:
            upcoming.append({"kind": d.kind.value, "label": _DATE_LABEL[d.kind], "in_days": in_days})
    stale_opps = []
    if rel is not None:
        for o in db.scalars(
            select(Opportunity).where(Opportunity.relationship_id == rel.id)
            .where(Opportunity.status.in_([OpportunityStatus.SUGGESTED, OpportunityStatus.CONFIRMED]))
            .where(Opportunity.stage.not_in([OpportunityStage.WON, OpportunityStage.LOST]))
        ).all():
            last = db.scalar(select(func.max(OpportunityActivity.occurred_at)).where(
                OpportunityActivity.opportunity_id == o.id))
            idle = (now - _aware(last or o.created_at)).days
            if idle >= STALE_OPPORTUNITY_DAYS:
                stale_opps.append((o.title, idle))
    days_since = (now - _aware(rel.last_interaction_at)).days if rel and rel.last_interaction_at else None
    return {
        "rel": rel, "interactions": interactions, "tasks": tasks, "upcoming": upcoming,
        "stale_opps": stale_opps, "days_since": days_since, "now": now,
        "ours": [c for c in open_cs if c.party == CommitmentParty.OURS],
        "theirs": [c for c in open_cs if c.party == CommitmentParty.THEIRS],
        "mutual": [c for c in open_cs if c.party == CommitmentParty.MUTUAL],
        "open": open_cs,
    }


def _raw_items(g: dict) -> list[dict]:
    """The suggestions the rules produce, before anyone's feedback is applied, most pressing first."""
    now: datetime = g["now"]
    mk = feedback_svc.make_item
    items: list[dict] = []
    overdue = [t for t in g["tasks"] if t.due_at and _aware(t.due_at) < now]
    for t in overdue:
        items.append(mk(TARGET_FOLLOWUP, "overdue_followup", f"Overdue follow-up: {t.title}"))
    for c in g["ours"] + g["mutual"]:
        items.append(mk(TARGET_TALKING_POINT, "close_commitment", f"Close your commitment: {c.text}"))
    for c in g["theirs"]:
        items.append(mk(TARGET_TALKING_POINT, "check_theirs", f"Check if they did: {c.text}"))
    for t in g["tasks"]:
        if t not in overdue:
            items.append(mk(TARGET_FOLLOWUP, "open_followup", f"Work the open follow-up: {t.title}"))
    for u in g["upcoming"]:
        when = "today" if u["in_days"] == 0 else f"in {u['in_days']} days"
        items.append(mk(TARGET_FOLLOWUP, "upcoming_date",
                        f"Their {u['label']} is {when} - a natural, non-sales reason to reach out."))
    last = g["interactions"][0] if g["interactions"] else None
    if last is not None and last.sentiment is Sentiment.NEGATIVE:
        items.append(mk(TARGET_TALKING_POINT, "steady_relationship",
                        "The last contact leaned negative - confirm it was closed out."))
    if g["days_since"] is not None and g["days_since"] >= settings.moment_inactivity_days:
        items.append(mk(TARGET_FOLLOWUP, "stale_contact",
                        f"No contact for {g['days_since']} days - a short check-in would keep it warm."))
    for title, idle in g["stale_opps"]:
        items.append(mk(TARGET_TALKING_POINT, "stale_opportunity",
                        f"Opportunity '{title}' has had no activity for {idle} days."))
    return items[:MAX_ITEMS]


def items_for_official(db: Session, official: Official) -> list[dict]:
    """Raw (unpersonalised) suggestions - what a feedback submission is validated against."""
    return _raw_items(_gather(db, official, datetime.now(timezone.utc)))


def build_for_official(db: Session, official: Official, user: User | None = None) -> dict:
    now = datetime.now(timezone.utc)
    g = _gather(db, official, now)
    rel: Relationship | None = g["rel"]
    unit = db.get(OrganizationUnit, official.organization_unit_id) if official.organization_unit_id else None

    # --- relationship memory: confirmed/unconfirmed facts + recent highlights from logged interactions ---
    memory: list[dict] = [
        {"fact": f.fact_text, "kind": "known_fact", "state": f.verification_state.value}
        for f in semantic_memory_svc.facts_for_official(db, official.id, limit=8)
    ]
    seen = {m["fact"].lower() for m in memory}
    cutoff = now - timedelta(days=settings.memory_lookback_days)
    for i in g["interactions"]:
        if _aware(i.occurred_at) < cutoff:
            continue
        for h in ((i.structured or i.ai_structured or {}).get("highlights") or []):
            if isinstance(h, str) and h.strip() and h.lower() not in seen:
                seen.add(h.lower())
                memory.append({"fact": h.strip(), "kind": "highlight", "state": None})

    d = lambda c: commitments_svc.commitment_dict(db, c)  # noqa: E731
    items, hidden = feedback_svc.apply_feedback(
        db, user.id if user is not None else None, SUBJECT_OFFICIAL, official.id, _raw_items(g)
    )
    return {
        "official": {"id": official.id, "name": official.name, "level": official.level,
                     "unit": unit.name if unit else None},
        "relationship": None if rel is None else {
            "id": rel.id, "status": rel.status.value, "importance": rel.importance.value,
            "score": rel.score, "band": band(rel.score)[0], "days_since_contact": g["days_since"],
        },
        "interactions": [
            {"id": i.id, "occurred_at": i.occurred_at.isoformat(), "type": i.type.value,
             "direction": i.direction.value, "sentiment": i.sentiment.value,
             "summary": i.ai_summary or ((i.raw_notes[:180] + "...") if i.raw_notes else "")}
            for i in g["interactions"]
        ],
        "memory": memory[:20],
        # You = the DC (ours / mutual); They = the official.
        "commitments": {
            "ours": [d(c) for c in g["ours"]], "theirs": [d(c) for c in g["theirs"]],
            "mutual": [d(c) for c in g["mutual"]], "total": len(g["open"]),
        },
        "proposed_commitments": [d(c) for c in commitments_svc.list_for_official(db, official.id, proposed_only=True)],
        "followups": [
            {"id": t.id, "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None,
             "overdue": bool(t.due_at and _aware(t.due_at) < now)}
            for t in g["tasks"]
        ],
        "upcoming_dates": g["upcoming"],
        "talking_point_items": [i for i in items if i["type"] == TARGET_TALKING_POINT],
        "followup_suggestion_items": [i for i in items if i["type"] == TARGET_FOLLOWUP],
        "suppressed_count": hidden,
    }
