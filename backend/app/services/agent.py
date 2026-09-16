"""The autonomous agent — Level 0-1 (observe + recommend only).

For each relationship evaluated, this reuses ``brief.build`` for context
(exactly what a human reviewing the relationship would see) and makes at most
one LLM call to propose a short list of schema-validated recommendations,
falling back to a deterministic rule-based stub when no LLM endpoint is
configured or the call fails/returns nothing usable — the same
gather-then-synthesize-with-fallback shape ``supervisor.py`` and
``llm.extract_interaction`` already use elsewhere in this codebase.

A recommendation is never itself a domain write. It only becomes one (a real
Task, a drafted EngagementMoment, a confirmed Connection) when a human calls
``approve()`` — see the module docstring on ``approve`` for exactly which
existing service function each recommendation type reuses.

Episodic memory: every past recommendation (approved, rejected or expired)
already lives in ``agent_recommendations`` - no separate memory store is
needed. ``_recent_history`` reads a relationship's past decisions and hands
them to the LLM as context; ``_recently_rejected`` makes an explicit human
rejection "stick" for a cooldown window instead of immediately re-proposing
the same type of recommendation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.agent import (
    AgentRecommendation,
    AgentRun,
    AgentRunScope,
    AgentRunStatus,
    AgentTrigger,
    RecommendationStatus,
    RecommendationType,
    RiskTier,
)
from ..models.engagement_moment import EngagementMoment, MomentStatus, MomentType
from ..models.opportunity import OpportunityStatus
from ..models.relationship import Relationship
from ..models.user import User
from . import audit, llm
from . import brief as brief_svc
from . import moments as moments_svc
from . import opportunities as opportunities_svc
from . import portfolio
from . import tasks as tasks_svc

settings = get_settings()

_MAX_RECOMMENDATIONS_PER_RELATIONSHIP = 5
_STALE_OPPORTUNITY_DAYS = 14


class RecommendationDraft(BaseModel):
    type: RecommendationType
    risk_tier: RiskTier = RiskTier.LOW
    reasoning: str
    payload: dict = Field(default_factory=dict)


class RecommendationSet(BaseModel):
    recommendations: list[RecommendationDraft] = Field(default_factory=list)


_RECOMMEND_SYSTEM = (
    "You review a structured relationship brief for a CRM and propose at most 3 "
    "concrete recommendations for the relationship owner to consider. Nothing is "
    "sent or created automatically - a human reviews and approves each one "
    "separately. Use ONLY the facts given; never invent a name, date, or fact "
    "that isn't in the data. An empty list is a valid and often correct answer - "
    "only propose something the data clearly supports.\n\n"
    'Reply with ONLY a JSON object: {"recommendations": [{"type": one of '
    '"create_task" | "draft_moment" | "create_opportunity", "risk_tier": one of '
    '"low" | "medium" | "high", "reasoning": a one-sentence "why now" explanation '
    'grounded in the data, "payload": {...}}]}.\n'
    'For "create_task", payload is {"title": string, "due_in_days": integer}. '
    'A create_task can address an open commitment, OR a stalled entry in '
    "open_opportunities (confirmed, but no activity for a while) - when it's the "
    "latter, name the opportunity by its title in the reasoning. "
    'For "draft_moment", payload is {"moment_type": one of the "type" values '
    'already listed under this relationship\'s open_moments - never propose a '
    "moment_type that isn't already present there, and never propose draft_moment "
    'if open_moments is empty. For "create_opportunity", payload is {"title": '
    'string, "detail": string (optional)} - only propose this when the recent '
    "interaction summaries clearly state a potential new business need (e.g. "
    "interest in a new product, an expansion, an upsell/cross-sell signal), never "
    "for routine relationship maintenance.\n\n"
    "You may also be given agent_history: past recommendations already made for "
    "this same relationship (type, reasoning, status, decided_at). Use it as "
    "memory, not as new evidence - never repeat something already marked "
    "'approved' (it already happened), and never propose something "
    "substantially the same as one marked 'rejected' - a human already said no "
    "to that."
)


def _llm_recommend(brief: dict, history: list[dict]) -> list[RecommendationDraft]:
    payload = {**brief, "agent_history": history}
    text = llm.chat(_RECOMMEND_SYSTEM, json.dumps(payload, default=str))
    if not text:
        return []
    try:
        data = json.loads(llm._json_blob(text))
        parsed = RecommendationSet.model_validate(data)
    except Exception:
        return []
    return parsed.recommendations[:_MAX_RECOMMENDATIONS_PER_RELATIONSHIP]


def _stub_recommend(brief: dict) -> list[RecommendationDraft]:
    """Deterministic fallback so the agent stays usable and demoable without an
    LLM endpoint configured, same principle as llm._stub_extract."""
    out: list[RecommendationDraft] = []

    reconnect = brief.get("reconnect_opportunity") or {}
    if reconnect.get("yes") and not brief.get("open_followups"):
        out.append(
            RecommendationDraft(
                type=RecommendationType.CREATE_TASK,
                risk_tier=RiskTier.LOW,
                reasoning=reconnect.get("reason") or brief.get("next_interaction") or "Reconnect opportunity detected.",
                payload={"title": (brief.get("next_interaction") or "Follow up")[:280], "due_in_days": 3},
            )
        )

    for opp in brief.get("open_opportunities") or []:
        days = opp.get("days_since_activity")
        if opp.get("status") == "confirmed" and isinstance(days, int) and days >= _STALE_OPPORTUNITY_DAYS:
            out.append(
                RecommendationDraft(
                    type=RecommendationType.CREATE_TASK,
                    risk_tier=RiskTier.LOW,
                    reasoning=f"The '{opp['title']}' opportunity has had no activity in {days} days.",
                    payload={"title": f"Follow up on the '{opp['title']}' opportunity", "due_in_days": 2},
                )
            )
            break  # one stalled-opportunity nudge per run is enough for the stub

    for m in brief.get("open_moments") or []:
        if m.get("status") == "detected" and not m.get("suppressed"):
            kind = str(m.get("type") or "").replace("_", " ")
            out.append(
                RecommendationDraft(
                    type=RecommendationType.DRAFT_MOMENT,
                    risk_tier=RiskTier.MEDIUM,
                    reasoning=f"A {kind} moment was detected and hasn't been drafted yet.",
                    payload={"moment_type": m.get("type")},
                )
            )

    # Same opportunity-hint vocabulary the interaction extractor already uses
    # (services/llm.py) - applied here to the Brief's own recent-interaction
    # summaries, so the agent can flag a business opportunity it notices while
    # reviewing a relationship, same as it does for tasks and moments.
    for i in brief.get("recent_interactions") or []:
        summary = str(i.get("summary") or "")
        low = summary.lower()
        if summary and any(h in low for h in llm._OPPORTUNITY_HINTS):
            out.append(
                RecommendationDraft(
                    type=RecommendationType.CREATE_OPPORTUNITY,
                    risk_tier=RiskTier.MEDIUM,
                    reasoning=summary[:300],
                    payload={"title": summary[:300]},
                )
            )
            break  # one candidate per run is enough for the stub

    return out


def _gather_drafts(brief: dict, history: list[dict]) -> tuple[list[RecommendationDraft], str, bool]:
    """Returns (drafts, model label, whether an LLM call actually produced them).
    ``history`` (past decisions for this relationship) only goes to the LLM -
    the stub's dedup against it happens uniformly afterwards in
    evaluate_relationship, regardless of which path produced the draft."""
    if settings.llm_base_url:
        try:
            drafts = _llm_recommend(brief, history)
        except Exception:
            drafts = []
        if drafts:
            return drafts, settings.llm_model, True
        return _stub_recommend(brief), f"stub (fallback from {settings.llm_model})", False
    return _stub_recommend(brief), "stub", False


def _resolve_payload(db: Session, rel: Relationship, draft: RecommendationDraft) -> dict | None:
    """Grounds a draft's payload against real data, or returns None to drop it
    entirely - e.g. a draft_moment recommendation is only kept if a matching
    DETECTED EngagementMoment genuinely exists; the agent never fabricates one."""
    if draft.type is RecommendationType.DRAFT_MOMENT:
        try:
            moment_type = MomentType(draft.payload.get("moment_type"))
        except ValueError:
            return None
        moment = db.scalar(
            select(EngagementMoment)
            .where(EngagementMoment.relationship_id == rel.id)
            .where(EngagementMoment.type == moment_type)
            .where(EngagementMoment.status == MomentStatus.DETECTED)
        )
        if moment is None:
            return None
        return {"moment_id": moment.id, "moment_type": moment_type.value}

    if draft.type is RecommendationType.CREATE_OPPORTUNITY:
        # Relationship-level dedup, not title-exact: two independent
        # extractions (this Brief scan vs. the interaction-level detector)
        # rarely phrase the same underlying signal identically, so matching
        # on exact title would let near-duplicates through. If the
        # relationship already has any opportunity in flight, don't add
        # another - a human already has one to review.
        if opportunities_svc.has_open_for_relationship(db, rel.id):
            return None
        payload = dict(draft.payload or {})
        payload.setdefault("title", draft.reasoning[:280])
        return payload

    # only remaining type is CREATE_TASK - just needs a title, defaulted from
    # the reasoning, since approving it calls a self-sufficient create.
    payload = dict(draft.payload or {})
    payload.setdefault("title", draft.reasoning[:280])
    return payload


def _evidence_for(brief: dict, rec_type: RecommendationType) -> dict:
    if rec_type is RecommendationType.CREATE_TASK:
        return {
            "trigger": (brief.get("reconnect_opportunity") or {}).get("reason"),
            "days_since_last_contact": brief.get("days_since_last_contact"),
            "score": brief.get("score"),
            "band": brief.get("band"),
        }
    if rec_type is RecommendationType.CREATE_OPPORTUNITY:
        return {
            "score": brief.get("score"),
            "band": brief.get("band"),
            "days_since_last_contact": brief.get("days_since_last_contact"),
        }
    # only remaining type is DRAFT_MOMENT
    return {
        "score": brief.get("score"),
        "band": brief.get("band"),
        "open_moments": brief.get("open_moments"),
    }


def _existing_pending(db: Session, relationship_id: int, rec_type: RecommendationType) -> bool:
    return (
        db.scalar(
            select(AgentRecommendation.id)
            .where(AgentRecommendation.relationship_id == relationship_id)
            .where(AgentRecommendation.type == rec_type)
            .where(AgentRecommendation.status == RecommendationStatus.PENDING)
        )
        is not None
    )


def _recently_rejected(
    db: Session, relationship_id: int, rec_type: RecommendationType, within_days: int
) -> bool:
    """Episodic memory in miniature: an explicit human rejection of this
    recommendation type for this relationship sticks for a cooldown window,
    instead of the agent immediately proposing the same type again next run."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    return (
        db.scalar(
            select(AgentRecommendation.id)
            .where(AgentRecommendation.relationship_id == relationship_id)
            .where(AgentRecommendation.type == rec_type)
            .where(AgentRecommendation.status == RecommendationStatus.REJECTED)
            .where(AgentRecommendation.decided_at >= cutoff)
        )
        is not None
    )


def _recent_history(db: Session, relationship_id: int, limit: int = 5) -> list[dict]:
    """Past decided recommendations for this relationship (approved/rejected/
    expired) - the LLM's view into what's already been tried. Reuses
    agent_recommendations directly rather than a separate memory store."""
    rows = db.scalars(
        select(AgentRecommendation)
        .where(AgentRecommendation.relationship_id == relationship_id)
        .where(AgentRecommendation.status != RecommendationStatus.PENDING)
        .order_by(AgentRecommendation.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "type": r.type.value,
            "reasoning": r.reasoning,
            "status": r.status.value,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        }
        for r in rows
    ]


def _note_tool(run: AgentRun, name: str) -> None:
    if name not in run.tools_used:
        run.tools_used = [*run.tools_used, name]


def evaluate_relationship(db: Session, rel: Relationship, run: AgentRun) -> list[AgentRecommendation]:
    brief = brief_svc.build(db, rel)
    _note_tool(run, "brief.build")

    history = _recent_history(db, rel.id)
    if history:
        _note_tool(run, "agent_history")

    drafts, model_used, used_llm = _gather_drafts(brief, history)
    run.model = model_used
    if used_llm:
        _note_tool(run, "llm.chat")

    created: list[AgentRecommendation] = []
    for draft in drafts[:_MAX_RECOMMENDATIONS_PER_RELATIONSHIP]:
        if _existing_pending(db, rel.id, draft.type) or _recently_rejected(
            db, rel.id, draft.type, settings.agent_rejection_cooldown_days
        ):
            continue
        payload = _resolve_payload(db, rel, draft)
        if payload is None:
            continue

        rec = AgentRecommendation(
            run_id=run.id,
            relationship_id=rel.id,
            official_id=rel.official_id,
            type=draft.type,
            risk_tier=draft.risk_tier,
            reasoning=draft.reasoning[:2000],
            evidence=_evidence_for(brief, draft.type),
            payload=payload,
            status=RecommendationStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.agent_recommendation_ttl_days),
        )
        db.add(rec)
        db.flush()
        audit.record(
            db,
            action="agent.recommendation.created",
            entity_type="agent_recommendation",
            entity_id=rec.id,
            actor_id=run.requested_by,
            after={"type": draft.type.value, "relationship_id": rel.id, "risk_tier": draft.risk_tier.value},
        )
        created.append(rec)
    return created


def _start_run(
    db: Session, *, trigger: AgentTrigger, scope: AgentRunScope, relationship_id: int | None, requested_by: int | None
) -> AgentRun:
    now = datetime.now(timezone.utc)
    run = AgentRun(
        trigger=trigger,
        scope=scope,
        relationship_id=relationship_id,
        requested_by=requested_by,
        status=AgentRunStatus.RUNNING,
        started_at=now,
    )
    db.add(run)
    db.flush()
    audit.record(
        db,
        action="agent.run.started",
        entity_type="agent_run",
        entity_id=run.id,
        actor_id=requested_by,
        after={"trigger": trigger.value, "scope": scope.value, "relationship_id": relationship_id},
    )
    return run


def _finish_run(db: Session, run: AgentRun, *, status: AgentRunStatus, error: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    run.status = status
    run.error = error
    run.finished_at = now
    started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
    run.duration_ms = int((now - started).total_seconds() * 1000)
    db.flush()
    audit.record(
        db,
        action=f"agent.run.{status.value}",
        entity_type="agent_run",
        entity_id=run.id,
        actor_id=run.requested_by,
        after={
            "relationships_considered": run.relationships_considered,
            "recommendations_created": run.recommendations_created,
            "error": error,
        },
    )


def _run_portfolio_body(db: Session, run: AgentRun, actor: User | None) -> None:
    rows = portfolio.scan(db, actor, limit=settings.agent_portfolio_scan_limit)
    _note_tool(run, "portfolio.scan")

    considered = rows[: settings.agent_max_relationships_per_run]
    rel_ids = [row["relationship_id"] for row in considered]
    rels_by_id: dict[int, Relationship] = {}
    if rel_ids:
        rels_by_id = {
            r.id: r for r in db.scalars(select(Relationship).where(Relationship.id.in_(rel_ids)))
        }

    total_recs = 0
    for row in considered:
        rel = rels_by_id.get(row["relationship_id"])
        if rel is None:
            continue
        total_recs += len(evaluate_relationship(db, rel, run))

    run.relationships_considered = len(considered)
    run.recommendations_created = total_recs


def run_for_relationship(db: Session, rel: Relationship, *, actor: User | None, trigger: AgentTrigger) -> AgentRun:
    run = _start_run(
        db,
        trigger=trigger,
        scope=AgentRunScope.RELATIONSHIP,
        relationship_id=rel.id,
        requested_by=actor.id if actor else None,
    )
    try:
        recs = evaluate_relationship(db, rel, run)
        run.relationships_considered = 1
        run.recommendations_created = len(recs)
        _finish_run(db, run, status=AgentRunStatus.COMPLETED)
    except Exception as exc:  # defensive: a run should never 500 the request
        _finish_run(db, run, status=AgentRunStatus.FAILED, error=str(exc)[:2000])
    return run


def run_for_portfolio(db: Session, actor: User, *, trigger: AgentTrigger) -> AgentRun:
    run = _start_run(
        db, trigger=trigger, scope=AgentRunScope.PORTFOLIO, relationship_id=None, requested_by=actor.id
    )
    try:
        _run_portfolio_body(db, run, actor)
        _finish_run(db, run, status=AgentRunStatus.COMPLETED)
    except Exception as exc:
        _finish_run(db, run, status=AgentRunStatus.FAILED, error=str(exc)[:2000])
    return run


def run_nightly(db: Session) -> AgentRun:
    """System-wide portfolio run with no owning actor - sees every relationship,
    same as an admin's portfolio scan. Called from the nightly scheduler job."""
    run = _start_run(
        db, trigger=AgentTrigger.NIGHTLY, scope=AgentRunScope.PORTFOLIO, relationship_id=None, requested_by=None
    )
    try:
        _run_portfolio_body(db, run, None)
        _finish_run(db, run, status=AgentRunStatus.COMPLETED)
    except Exception as exc:
        _finish_run(db, run, status=AgentRunStatus.FAILED, error=str(exc)[:2000])
    return run


def approve(db: Session, rec: AgentRecommendation, actor: User) -> AgentRecommendation:
    """Turns an approved recommendation into the real write it stood in for,
    using the exact same service function a human-initiated action would use:

    - CREATE_TASK -> services.tasks.create_task (same path routes/tasks.py uses)
    - DRAFT_MOMENT -> moments.build_draft on the SAME EngagementMoment row the
      recommendation pointed at (never a new one), landing it at DRAFT_READY -
      it then still needs its own separate human approval/send via the existing
      /moments endpoints. Approving the recommendation only means "yes, prepare
      this draft," not "send it."
    - CREATE_OPPORTUNITY -> services.opportunities.upsert(status=CONFIRMED),
      the same path routes/opportunities.py's manual-create endpoint uses -
      lands CONFIRMED directly (approving the recommendation already is the
      human confirmation), not SUGGESTED.
    """
    result_ref: dict | None = None
    rel = db.get(Relationship, rec.relationship_id)

    if rec.type is RecommendationType.CREATE_TASK and rel is not None:
        due_at = None
        due_in_days = rec.payload.get("due_in_days")
        if isinstance(due_in_days, (int, float)):
            due_at = datetime.now(timezone.utc) + timedelta(days=due_in_days)
        task = tasks_svc.create_task(
            db,
            relationship=rel,
            title=rec.payload.get("title") or rec.reasoning[:280],
            detail=rec.reasoning,
            due_at=due_at,
            actor_id=actor.id,
        )
        result_ref = {"task_id": task.id}

    elif rec.type is RecommendationType.DRAFT_MOMENT:
        moment = db.get(EngagementMoment, rec.payload.get("moment_id"))
        if moment is not None and moment.status is MomentStatus.DETECTED:
            sender_name = None
            if rel is not None and rel.owner_id:
                owner = db.get(User, rel.owner_id)
                sender_name = owner.name if owner else None
            moment.draft_text = moments_svc.build_draft(db, moment, sender_name)
            moment.status = MomentStatus.DRAFT_READY
            result_ref = {"moment_id": moment.id}
        elif moment is not None:
            result_ref = {"moment_id": moment.id, "note": f"moment already {moment.status.value}"}

    elif rec.type is RecommendationType.CREATE_OPPORTUNITY and rel is not None:
        opp, _ = opportunities_svc.upsert(
            db,
            relationship=rel,
            title=rec.payload.get("title") or rec.reasoning[:280],
            detail=rec.reasoning,
            source="Agent recommendation",
            status=OpportunityStatus.CONFIRMED,
            actor_id=actor.id,
        )
        result_ref = {"opportunity_id": opp.id}

    rec.status = RecommendationStatus.APPROVED
    rec.decided_by = actor.id
    rec.decided_at = datetime.now(timezone.utc)
    rec.result_ref = result_ref
    db.flush()
    audit.record(
        db,
        action="agent.recommendation.approved",
        entity_type="agent_recommendation",
        entity_id=rec.id,
        actor_id=actor.id,
        after={"type": rec.type.value, "result_ref": result_ref},
    )
    return rec


def reject(db: Session, rec: AgentRecommendation, actor: User, reason: str | None) -> AgentRecommendation:
    rec.status = RecommendationStatus.REJECTED
    rec.decided_by = actor.id
    rec.decided_at = datetime.now(timezone.utc)
    if reason:
        rec.result_ref = {"reason": reason}
    db.flush()
    audit.record(
        db,
        action="agent.recommendation.rejected",
        entity_type="agent_recommendation",
        entity_id=rec.id,
        actor_id=actor.id,
        after={"reason": reason},
    )
    return rec


def expire_stale_recommendations(db: Session) -> int:
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(AgentRecommendation)
        .where(AgentRecommendation.status == RecommendationStatus.PENDING)
        .where(AgentRecommendation.expires_at.is_not(None))
        .where(AgentRecommendation.expires_at < now)
    ).all()
    for rec in rows:
        rec.status = RecommendationStatus.EXPIRED
        audit.record(
            db,
            action="agent.recommendation.expired",
            entity_type="agent_recommendation",
            entity_id=rec.id,
            after={"type": rec.type.value},
        )
    db.flush()
    return len(rows)
