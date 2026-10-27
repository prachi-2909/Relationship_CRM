"""Pre-Call Intelligence: everything the RM should know before dialling a CSP, in one place.

Integrates the three pillars: open COMMITMENTS (tracked), relationship MEMORY (durable facts built
from the CSP's retained call briefs), and the last conversation's context - then distils suggested
talking points. Read-only; it only reads what is already stored, which is exactly why retaining
RM-KO briefs matters: the memory and the open loops are built from them.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.call_intelligence import CallSession
from ..models.commitment import Commitment, CommitmentParty, CommitmentStatus
from ..models.csp import Csp
from . import commitments as commitments_svc

settings = get_settings()

_PENDING = re.compile(r"pending|remaining|not yet|yet to|issue|expiry|follow|overdue|short", re.I)
_SLAB = re.compile(r"slab", re.I)


def build_for_csp(db: Session, csp: Csp) -> dict:
    calls = db.scalars(
        select(CallSession)
        .where(CallSession.csp_id == csp.id)
        .order_by(CallSession.started_at.desc())
        .limit(50)
    ).all()
    briefs = [(c, c.analysis.analysis_json or {}) for c in calls if c.analysis is not None]

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
    last_call = briefs[0] if briefs else None
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

    # --- open commitments -------------------------------------------------------------------
    open_cs = commitments_svc.list_for_csp(db, csp.id, include_closed=False)
    ours = [_commitment_dict(c) for c in open_cs if c.party == CommitmentParty.OURS]
    theirs = [_commitment_dict(c) for c in open_cs if c.party == CommitmentParty.THEIRS]
    mutual = [_commitment_dict(c) for c in open_cs if c.party == CommitmentParty.MUTUAL]
    proposed = [_commitment_dict(c) for c in commitments_svc.list_for_csp(db, csp.id, proposed_only=True)]

    # --- current slab / product status (latest brief) ---------------------------------------
    slab_status = []
    if last_call is not None:
        for h in (last_call[1].get("highlights") or []):
            if isinstance(h, str) and _SLAB.search(h):
                slab_status.append(h.strip())

    # --- suggested talking points -----------------------------------------------------------
    talking: list[str] = []
    for c in ours + mutual:
        talking.append(f"Close your commitment: {c['text']}")
    for c in theirs:
        talking.append(f"Check if they did: {c['text']}")
    if last_call is not None:
        for h in (last_call[1].get("highlights") or []):
            if isinstance(h, str) and _PENDING.search(h) and h.strip() not in [t.split(": ", 1)[-1] for t in talking]:
                talking.append(f"Pending from last call: {h.strip()}")

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
        "open_commitments": {"ours": ours, "theirs": theirs, "mutual": mutual, "total": len(open_cs)},
        # AI suggestions awaiting the RM's accept/dismiss - deliberately NOT part of talking points.
        "proposed_commitments": proposed,
        "slab_status": slab_status,
        "memory": memory[:20],
        "talking_points": talking[:10],
    }


def _commitment_dict(c: Commitment) -> dict:
    return {
        "id": c.id,
        "text": c.text,
        "party": c.party.value,
        "due_date": c.due_date.isoformat() if c.due_date else None,
        "status": c.status.value,
        "source": c.source,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
