"""Relationship Brief — a read-only synthesis of one relationship.

Composes the answers the CRM is meant to help with: what matters about this
relationship, what has changed, whether there's an opening to reconnect, and
what the next interaction should be. Assembled from data already in the system;
no writes. A human reads it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.engagement_moment import EngagementMoment, MomentStatus, MomentType
from ..models.interaction import Interaction, Sentiment
from ..models.official_date import DateKind, OfficialDate
from ..models.organization_unit import OrganizationUnit
from ..models.relationship import Relationship, RelationshipScoreHistory, RelationshipStatus
from ..models.task import Task, TaskStatus
from ..models.connection import ConnectionStatus
from ..services import connections as connections_svc
from ..services import importance as importance_svc
from ..services import llm
from ..services.scoring import band

settings = get_settings()

_OPEN_MOMENT_STATUSES = (
    MomentStatus.DETECTED,
    MomentStatus.DRAFT_READY,
    MomentStatus.APPROVED,
)
_ACTIVE_PLUS = {
    RelationshipStatus.ACTIVE,
    RelationshipStatus.STRONG,
    RelationshipStatus.STRATEGIC,
    RelationshipStatus.DEVELOPING,
}
_GREETING_MOMENTS = {
    MomentType.BIRTHDAY,
    MomentType.WORK_ANNIVERSARY,
    MomentType.PROMOTION,
}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_since_contact(rel: Relationship, now: datetime) -> int | None:
    if rel.last_interaction_at is None:
        return None
    return (now - _aware(rel.last_interaction_at)).days


def _next_occurrence(anniversary: date, today: date) -> date:
    year = today.year
    try:
        cand = anniversary.replace(year=year)
    except ValueError:
        cand = anniversary.replace(year=year, day=28)
    if cand < today:
        try:
            cand = anniversary.replace(year=year + 1)
        except ValueError:
            cand = anniversary.replace(year=year + 1, day=28)
    return cand


def build(db: Session, rel: Relationship) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    official = rel.official
    unit = (
        db.get(OrganizationUnit, official.organization_unit_id)
        if official.organization_unit_id
        else None
    )
    days_since = _days_since_contact(rel, now)
    label, _ = band(rel.score)

    # --- interactions (recent) -------------------------------------------
    interactions = db.scalars(
        select(Interaction)
        .where(Interaction.relationship_id == rel.id)
        .order_by(Interaction.occurred_at.desc())
        .limit(8)
    ).all()
    recent_interactions = [
        {
            "occurred_at": i.occurred_at.isoformat(),
            "type": i.type.value,
            "direction": i.direction.value,
            "sentiment": i.sentiment.value,
            "summary": i.ai_summary or (i.raw_notes[:180] + "…" if i.raw_notes else ""),
        }
        for i in interactions[:5]
    ]

    since_90 = now - timedelta(days=90)
    win = [i for i in interactions if _aware(i.occurred_at) >= since_90]
    commitments: list[str] = []
    people: list[str] = []
    for i in win:
        for c in (i.structured or {}).get("commitments", []):
            if c not in commitments:
                commitments.append(c)
        for p in (i.structured or {}).get("people", []):
            if p not in people:
                people.append(p)

    # --- stakeholder graph ------------------------------------------
    graph = connections_svc.neighbors(
        db, official.id, statuses=(ConnectionStatus.CONFIRMED, ConnectionStatus.SUGGESTED)
    )
    confirmed_edges = [g for g in graph if g["status"] == "confirmed"]
    suggested_count = sum(1 for g in graph if g["status"] == "suggested")
    linked_names = {g["name"] for g in graph}
    unlinked_mentions = [p for p in people if p not in linked_names][:10]

    # --- score trend ---------------------------------------------------
    history = db.scalars(
        select(RelationshipScoreHistory)
        .where(RelationshipScoreHistory.relationship_id == rel.id)
        .order_by(RelationshipScoreHistory.computed_at.desc())
        .limit(2)
    ).all()
    score_delta = (
        history[0].score - history[1].score if len(history) >= 2 else 0
    )

    # --- follow-ups --------------------------------------------------
    open_tasks = db.scalars(
        select(Task)
        .where(Task.relationship_id == rel.id)
        .where(Task.status == TaskStatus.OPEN)
        .order_by(Task.due_at.is_(None), Task.due_at)
    ).all()
    open_followups = [
        {
            "title": t.title,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "overdue": bool(t.due_at and _aware(t.due_at) < now),
        }
        for t in open_tasks
    ]
    overdue = [f for f in open_followups if f["overdue"]]

    # --- moments ---------------------------------------------------
    moments = db.scalars(
        select(EngagementMoment)
        .where(EngagementMoment.relationship_id == rel.id)
        .where(EngagementMoment.status.in_(_OPEN_MOMENT_STATUSES))
        .order_by(EngagementMoment.created_at.desc())
    ).all()
    open_moments = [
        {
            "type": m.type.value,
            "status": m.status.value,
            "trigger": (m.evidence or {}).get("trigger"),
            "suppressed": bool(m.suppressed_reason),
        }
        for m in moments
    ]
    approved_moment = next((m for m in moments if m.status is MomentStatus.APPROVED), None)
    greeting_moment = next((m for m in moments if m.type in _GREETING_MOMENTS), None)

    # --- upcoming dated facts -------------------------------------
    upcoming_dates = []
    for d in db.scalars(
        select(OfficialDate).where(OfficialDate.official_id == official.id)
    ):
        if d.kind is DateKind.PROMOTED:
            continue
        nxt = _next_occurrence(d.value, today)
        in_days = (nxt - today).days
        if 0 <= in_days <= 60:
            upcoming_dates.append(
                {"kind": d.kind.value, "date": nxt.isoformat(), "in_days": in_days}
            )

    # --- what is important -----------------------------------------
    _, imp_reasons = importance_svc.compute(db, rel)
    lean = imp_reasons["sentiment"]["lean"]
    imp_bits = [f"{rel.importance.value.capitalize()} relationship."]
    if imp_reasons["base_tier"] >= 2 and official.level:
        imp_bits.append(f"Seniority: {official.level}.")
    if imp_reasons["sentiment"]["bump"]:
        imp_bits.append("Engagement has been consistently positive, which raised its priority.")
    elif lean < 0:
        imp_bits.append("Recent engagement has leaned negative — worth steadying.")
    imp_bits.append(f"Health is {label.lower()} (score {rel.score}).")
    what_is_important = " ".join(imp_bits)

    # --- what changed --------------------------------------------
    changed: list[str] = []
    if score_delta:
        changed.append(
            f"Health score {score_delta:+d} "
            f"({history[1].score} → {history[0].score})."
        )
    recent_moment = next(
        (m for m in moments if _aware(m.created_at) >= now - timedelta(days=14)), None
    )
    if recent_moment:
        changed.append(f"New '{recent_moment.type.value}' moment detected.")
    if interactions and interactions[0].sentiment is Sentiment.NEGATIVE:
        changed.append("The most recent interaction was negative in tone.")
    if days_since is not None and days_since >= 30:
        changed.append(f"No contact for {days_since} days.")
    if not changed:
        changed.append("No notable change in the last two weeks.")

    # --- reconnect opportunity ----------------------------------
    soon_greeting = next(
        (
            d
            for d in upcoming_dates
            if d["kind"] in ("birthday", "joined") and d["in_days"] <= 30
        ),
        None,
    )
    last_negative = bool(interactions and interactions[0].sentiment is Sentiment.NEGATIVE)
    reconnect_yes = False
    reconnect_reason = "No pressing reason to reach out right now."
    if greeting_moment is not None:
        reconnect_yes = True
        reconnect_reason = (
            f"An upcoming {greeting_moment.type.value.replace('_', ' ')} is a natural, "
            f"non-sales reason to reach out."
        )
    elif soon_greeting is not None:
        kind = "work anniversary" if soon_greeting["kind"] == "joined" else "birthday"
        reconnect_yes = True
        reconnect_reason = (
            f"Their {kind} is in {soon_greeting['in_days']} days — a natural, "
            f"non-sales reason to reach out."
        )
    elif (
        days_since is not None
        and days_since >= settings.moment_inactivity_days
        and rel.status in _ACTIVE_PLUS
    ):
        reconnect_yes = True
        reconnect_reason = (
            f"It has been {days_since} days since the last contact on an active "
            f"relationship — the thread is going cold."
        )
    elif last_negative and days_since is not None and days_since >= 5:
        reconnect_yes = True
        reconnect_reason = (
            "The last contact was negative and nothing has closed it out since — "
            "worth following up to steady the relationship."
        )
    elif (
        interactions
        and interactions[0].sentiment is Sentiment.POSITIVE
        and days_since is not None
        and days_since >= 14
    ):
        reconnect_yes = True
        reconnect_reason = (
            "The last contact was positive but there has been a gap since — a good "
            "moment to build on it."
        )
    elif commitments:
        reconnect_yes = True
        reconnect_reason = "There is an open commitment that needs a follow-up."

    # --- next interaction --------------------------------------
    if overdue:
        next_interaction = f"Close the overdue follow-up: “{overdue[0]['title']}”."
    elif approved_moment is not None:
        next_interaction = (
            f"Send the approved {approved_moment.type.value.replace('_', ' ')} note "
            f"(already drafted) and record the outcome."
        )
    elif open_followups:
        next_interaction = f"Work the open follow-up: “{open_followups[0]['title']}”."
    elif commitments:
        next_interaction = f"Follow up on the commitment: “{commitments[0]}”."
    elif [m for m in open_moments if not m["suppressed"]]:
        next_interaction = "Review the open moment in the feed and decide on a draft."
    elif last_negative:
        next_interaction = (
            "Follow up on the unresolved thread from the last contact and confirm "
            "it is closed out."
        )
    elif reconnect_yes:
        next_interaction = "A brief, non-sales check-in to keep the relationship warm."
    else:
        next_interaction = "Nothing pressing — hold the regular cadence."

    brief = {
        "relationship_id": rel.id,
        "official_name": official.name,
        "official_level": official.level,
        "unit": unit.name if unit else None,
        "owner_id": rel.owner_id,
        "status": rel.status.value,
        "importance": rel.importance.value,
        "score": rel.score,
        "band": label,
        "days_since_last_contact": days_since,
        "what_is_important": what_is_important,
        "what_changed": changed,
        "reconnect_opportunity": {"yes": reconnect_yes, "reason": reconnect_reason},
        "next_interaction": next_interaction,
        "stakeholders": {
            "available": bool(confirmed_edges),
            "connections": [
                {
                    "official_id": g["official_id"],
                    "name": g["name"],
                    "level": g["level"],
                    "type": g["type"],
                    "direction": g["direction"],
                    "label": g["label"],
                    "note": g["note"],
                }
                for g in confirmed_edges
            ],
            "suggested_count": suggested_count,
            "mentioned": unlinked_mentions,
            "note": _stakeholder_note(confirmed_edges, suggested_count, unlinked_mentions),
        },
        "open_followups": open_followups,
        "recent_commitments": commitments[:8],
        "open_moments": open_moments,
        "upcoming_dates": upcoming_dates,
        "recent_interactions": recent_interactions,
    }
    brief["narrative"], brief["generated_by"] = _narrative(brief)
    return brief


def _stakeholder_note(
    confirmed: list[dict], suggested_count: int, mentions: list[str]
) -> str:
    if confirmed:
        note = f"{len(confirmed)} confirmed connection(s) in the graph."
    else:
        note = "No confirmed connections in the graph yet."
    if suggested_count:
        note += f" {suggested_count} suggested edge(s) awaiting review."
    if mentions:
        note += (
            f" Names mentioned in interactions but not yet linked to an "
            f"official: {', '.join(mentions)}."
        )
    return note


_BRIEF_SYSTEM = (
    "You are a relationship analyst for a CRM. Given a structured brief about one "
    "professional relationship, write a short, plain, actionable paragraph (4-6 "
    "sentences) for the relationship owner. Cover: what matters about this "
    "relationship, what has changed recently, whether there is an opening to "
    "reconnect, what the next interaction should be, and — if any are listed — who "
    "the key stakeholders around this person are and how to route through them. "
    "Be concrete and specific to the data given. No preamble, no headings, no "
    "bullet points."
)


def _narrative(brief: dict) -> tuple[str, str]:
    import json

    context = {
        k: brief[k]
        for k in (
            "official_name", "official_level", "unit", "status", "importance",
            "score", "band", "days_since_last_contact", "what_is_important",
            "what_changed", "reconnect_opportunity", "next_interaction",
            "stakeholders", "open_followups", "recent_commitments", "open_moments",
            "upcoming_dates", "recent_interactions",
        )
    }
    text = llm.chat(_BRIEF_SYSTEM, json.dumps(context, default=str))
    if text:
        return text, f"llm:{settings.llm_model}"

    # deterministic fallback — no endpoint configured (or it failed)
    lead = brief["official_name"]
    if brief["official_level"]:
        lead += f", {brief['official_level']}"
    if brief["unit"]:
        lead += f" at {brief['unit']}"
    sentences = [
        f"{lead}. {brief['what_is_important']}",
        " ".join(brief["what_changed"]),
    ]
    rec = brief["reconnect_opportunity"]
    sentences.append(
        ("Opportunity to reconnect: " + rec["reason"]) if rec["yes"] else rec["reason"]
    )
    sentences.append(f"Next: {brief['next_interaction']}")
    return " ".join(s for s in sentences if s), "template"
