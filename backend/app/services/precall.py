"""Pre-Call Intelligence: everything the RM should know before dialling a CSP, in one place.

Integrates the three pillars: open COMMITMENTS (tracked), relationship MEMORY (durable facts built
from the CSP's retained call briefs), and the last conversation's context - then distils suggested
talking points. Read-only; it only reads what is already stored, which is exactly why retaining
RM-KO briefs matters: the memory and the open loops are built from them.

Each talking point is an item {key, type, kind, text}; `kind` is what feedback is aggregated on, and the
viewer's own "not useful" verdicts are applied on top (see services/intelligence_feedback.py).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.call_intelligence import CallSession
from ..models.commitment import CommitmentParty
from ..models.csp import Csp
from ..models.intelligence_feedback import SUBJECT_CSP, TARGET_TALKING_POINT
from ..models.user import User
from . import commitments as commitments_svc
from . import intelligence_feedback as feedback_svc

settings = get_settings()

_PENDING = re.compile(r"pending|remaining|not yet|yet to|issue|expiry|follow|overdue|short", re.I)
_SLAB = re.compile(r"slab", re.I)
MAX_TALKING_POINTS = 10


def _gather(db: Session, csp: Csp) -> dict:
    calls = db.scalars(
        select(CallSession)
        .where(CallSession.csp_id == csp.id)
        .order_by(CallSession.started_at.desc())
        .limit(50)
    ).all()
    briefs = [(c, c.analysis.analysis_json or {}) for c in calls if c.analysis is not None]
    open_cs = commitments_svc.list_for_csp(db, csp.id, include_closed=False)
    return {
        "briefs": briefs,
        "last_call": briefs[0] if briefs else None,
        "open": open_cs,
        "ours": [c for c in open_cs if c.party == CommitmentParty.OURS],
        "theirs": [c for c in open_cs if c.party == CommitmentParty.THEIRS],
        "mutual": [c for c in open_cs if c.party == CommitmentParty.MUTUAL],
    }


def _raw_items(g: dict) -> list[dict]:
    """The talking points the rules currently produce, before anyone's feedback is applied."""
    items: list[dict] = []
    taken: set[str] = set()

    def add(kind: str, text: str, underlying: str) -> None:
        items.append(feedback_svc.make_item(TARGET_TALKING_POINT, kind, text))
        taken.add(underlying.strip())

    for c in g["ours"] + g["mutual"]:
        add("close_commitment", f"Close your commitment: {c.text}", c.text)
    for c in g["theirs"]:
        add("check_theirs", f"Check if they did: {c.text}", c.text)
    if g["last_call"] is not None:
        for h in g["last_call"][1].get("highlights") or []:
            if isinstance(h, str) and _PENDING.search(h) and h.strip() not in taken:
                add("pending_from_last_call", f"Pending from last call: {h.strip()}", h)
    return items[:MAX_TALKING_POINTS]


def items_for_csp(db: Session, csp: Csp) -> list[dict]:
    """Raw (unpersonalised) suggestions - what a feedback submission is validated against."""
    return _raw_items(_gather(db, csp))


def build_for_csp(db: Session, csp: Csp, user: User | None = None) -> dict:
    g = _gather(db, csp)
    briefs, last_call = g["briefs"], g["last_call"]

    # --- relationship memory: durable facts accumulated from retained briefs ----------------
    memory: list[dict] = []
    seen: set[str] = set()
    # Memory lifecycle: only briefs inside the lookback window feed it, so stale facts age out.
    memory_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.memory_lookback_days)
    memory_briefs = [
        (c, b) for c, b in briefs
        if (c.started_at if c.started_at.tzinfo else c.started_at.replace(tzinfo=timezone.utc)) >= memory_cutoff
    ]
    for call, brief in memory_briefs:
        for h in (brief.get("highlights") or []):
            if isinstance(h, str) and h.strip() and h.lower() not in seen:
                seen.add(h.lower())
                memory.append({"fact": h.strip(), "kind": "status", "from": call.started_at.isoformat()})
        for s in (brief.get("relationship_signals") or []):
            if isinstance(s, str) and s.strip() and s.lower() not in seen:
                seen.add(s.lower())
                memory.append({"fact": s.strip(), "kind": "signal", "from": call.started_at.isoformat()})

    # --- last conversation ------------------------------------------------------------------
    last = None
    if last_call is not None:
        call, brief = last_call
        last = {
            "call_id": call.id,
            "when": call.started_at.isoformat(),
            "direction": call.direction.value,
            "summary": brief.get("summary") or "",
            "highlights": [h for h in (brief.get("highlights") or []) if isinstance(h, str)][:8],
        }

    # --- the RM's own performance review (what / why / should be), from the latest brief that has one ----
    performance = None
    for call, brief in memory_briefs:
        perf = brief.get("performance")
        if isinstance(perf, dict) and any(perf.get(k) for k in ("what", "why", "should_be")):
            performance = {
                "what": list(perf.get("what") or []), "why": list(perf.get("why") or []),
                "should_be": list(perf.get("should_be") or []), "from": call.started_at.isoformat(),
            }
            break

    # --- commitments --------------------------------------------------------------------------
    d = lambda c: commitments_svc.commitment_dict(db, c)  # noqa: E731
    proposed = [d(c) for c in commitments_svc.list_for_csp(db, csp.id, proposed_only=True)]

    # --- current slab / product status (latest brief) ---------------------------------------
    slab_status = []
    if last_call is not None:
        for h in (last_call[1].get("highlights") or []):
            if isinstance(h, str) and _SLAB.search(h):
                slab_status.append(h.strip())

    # --- suggested talking points (with this viewer's own feedback applied) ---------------------
    items, hidden = feedback_svc.apply_feedback(
        db, user.id if user is not None else None, SUBJECT_CSP, csp.id, _raw_items(g)
    )

    return {
        "csp_id": csp.csp_id,
        "name": csp.name,
        "category": csp.category,
        "branch": csp.branch_name,
        "rm_name": csp.rm_name,
        "mobile": csp.mobile,
        "alternate_mobile": csp.alternate_mobile,
        "calls_count": len(briefs),
        "last_call": last,
        "open_commitments": {
            "ours": [d(c) for c in g["ours"]], "theirs": [d(c) for c in g["theirs"]],
            "mutual": [d(c) for c in g["mutual"]], "total": len(g["open"]),
        },
        # AI suggestions awaiting the RM's accept/dismiss - deliberately NOT part of talking points.
        "proposed_commitments": proposed,
        "slab_status": slab_status,
        # What the RM told the CSP last time: where they stand, why, and what it should be.
        "performance": performance,
        "memory": memory[:20],
        "talking_points": [i["text"] for i in items],      # kept for older clients
        "talking_point_items": items,
        "suppressed_count": hidden,
    }
