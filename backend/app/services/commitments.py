"""Commitment tracking: turn a call's AI brief into discrete, trackable commitments.

Extraction is idempotent per call - re-running never duplicates. Party (ours/theirs) is inferred
from the wording; a due date is parsed when the text states one. The same code serves RM-KO and
DC-SBI calls, tagging each commitment with its source_kind so retention/permission/audit stay
separable.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.call_intelligence import CallSession
from ..models.commitment import (
    Commitment,
    CommitmentParty,
    CommitmentSourceKind,
    CommitmentStatus,
)
from ..models.csp import Csp
from ..models.user import User
from . import audit

settings = get_settings()

# The subject at the start of a line is the strongest signal of who owns the promise
# ("CSP to fix…" = theirs, "RM to update…" = ours).
_SUBJECT_THEIRS = re.compile(r"^\s*(the\s+)?(csp|operator|bank\s*mitra|official|they|he|she|customer)\b", re.I)
_SUBJECT_OURS = re.compile(r"^\s*(the\s+)?(rm|relationship\s*manager|we|i|eko|our\s+team|officer)\b", re.I)
# Fallback: any mention of either side anywhere in the text.
_OURS = re.compile(r"\b(we|our|i will|i'll|rm|relationship manager|eko|officer)\b", re.I)
_THEIRS = re.compile(r"\b(csp|operator|bank mitra|official|customer|they|their)\b", re.I)


def _party(text: str, from_action_item: bool) -> CommitmentParty:
    # 1) Strongest signal: who the sentence is about at its start.
    if _SUBJECT_THEIRS.search(text):
        return CommitmentParty.THEIRS
    if _SUBJECT_OURS.search(text):
        return CommitmentParty.OURS
    # 2) Fall back to mentions anywhere.
    ours, theirs = bool(_OURS.search(text)), bool(_THEIRS.search(text))
    if theirs and not ours:
        return CommitmentParty.THEIRS
    if ours and not theirs:
        return CommitmentParty.OURS
    if theirs and ours:
        return CommitmentParty.MUTUAL
    # 3) Nothing clear: an action item is the officer's own next step; else unclear.
    return CommitmentParty.OURS if from_action_item else CommitmentParty.MUTUAL


# Language that signals something was only discussed / floated, not agreed. Such lines stay in the
# brief and the relationship memory, but are never turned into a tracked obligation.
_HEDGED = re.compile(
    r"\b(?:might|may|maybe|perhaps|possibly|probably|could|consider(?:ing)?|tentative(?:ly)?|"
    r"if time permits|if possible|would like to|will try|try(?:ing)? to|"
    r"not (?:yet )?(?:confirmed|decided|agreed|finali[sz]ed)|nothing (?:decided|agreed)|discussed)\b",
    re.I,
)


def is_hedged(text: str) -> bool:
    return bool(_HEDGED.search(text))


# Dates like "by 30th", "by 5 Nov", "before 2026-11-10", "within 3 days".
_DAY = re.compile(r"\bby\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _due_date(text: str, today: date) -> date | None:
    m = _ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _DAY.search(text)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            # Next occurrence of that day-of-month, this month or next.
            month, year = today.month, today.year
            if day < today.day:
                month += 1
                if month > 12:
                    month, year = 1, year + 1
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def _source_kind_for(call: CallSession) -> CommitmentSourceKind:
    return CommitmentSourceKind.RM_CSP if call.csp_id is not None else CommitmentSourceKind.DC_OFFICIAL


def extract_from_call(
    db: Session,
    call: CallSession,
    *,
    brief: dict | None = None,
    status: CommitmentStatus = CommitmentStatus.PROPOSED,
) -> list[Commitment]:
    """Create commitment records from a call's brief.

    The AI only PROPOSES: by default new records are PROPOSED and a human must accept them before they
    count as open obligations. Pass status=OPEN only when a human has just approved the brief (the DC
    confirm flow). Hedged wording ("might", "will try", "discussed") is never extracted.

    Re-running refreshes this call's still-PROPOSED records from the current brief (so a re-recorded
    brief replaces stale proposals) and never touches accepted/done/cancelled ones or duplicates a
    text the call already has.
    """
    brief = brief if brief is not None else (call.analysis.analysis_json if call.analysis else None)
    if not brief:
        return []

    # Refresh: drop this call's un-reviewed proposals; they are re-derived from the current brief.
    for stale in db.scalars(
        select(Commitment)
        .where(Commitment.call_session_id == call.id)
        .where(Commitment.status == CommitmentStatus.PROPOSED)
    ).all():
        db.delete(stale)
    db.flush()

    taken = {
        c.text.lower()[:200]
        for c in db.scalars(select(Commitment).where(Commitment.call_session_id == call.id)).all()
    }
    today = datetime.now(timezone.utc).date()
    source_kind = _source_kind_for(call)
    items: list[tuple[str, bool]] = []
    for c in brief.get("commitments") or []:
        if isinstance(c, str) and c.strip():
            items.append((c.strip(), False))
    for a in brief.get("action_items") or []:
        if isinstance(a, str) and a.strip():
            items.append((a.strip(), True))

    created: list[Commitment] = []
    for text, is_action in items:
        key = text.lower()[:200]
        if key in taken or is_hedged(text):
            continue
        taken.add(key)
        c = Commitment(
            call_session_id=call.id,
            csp_id=call.csp_id,
            official_id=call.official_id,
            relationship_id=call.relationship_id,
            owner_user_id=call.dc_user_id,
            text=text[:500],
            party=_party(text, is_action),
            due_date=_due_date(text, today),
            status=status,
            source="call_brief",
            source_kind=source_kind,
            created_by=call.dc_user_id,
        )
        db.add(c)
        created.append(c)
    if created:
        db.flush()
        audit.record(
            db, action="commitment.proposed" if status == CommitmentStatus.PROPOSED else "commitment.extracted",
            entity_type="call_session", entity_id=call.id,
            after={"count": len(created), "source_kind": source_kind.value, "status": status.value},
        )
    return created


def propose_for_new_brief(db: Session, call: CallSession) -> None:
    """Pipeline hook, called right after a call's brief is stored. Only RM-CSP calls get proposals here;
    a DC-official call gets its commitments when the DC confirms the brief. Best-effort: a failure here
    must never break transcription."""
    if call.csp_id is None:
        return
    try:
        db.flush()
        db.refresh(call)
        extract_from_call(db, call)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("rcrm.commitments").exception("commitment proposal failed for call %s", call.id)


def backfill_proposals(db: Session) -> int:
    """One-off: propose commitments for CSP calls whose brief existed before this feature (no GET path
    does this any more - reading a page must not write)."""
    n = 0
    for call in db.scalars(select(CallSession).where(CallSession.csp_id.is_not(None))).all():
        if call.analysis is not None and not db.scalars(
            select(Commitment).where(Commitment.call_session_id == call.id).limit(1)
        ).first():
            n += len(extract_from_call(db, call))
    db.commit()
    return n


def list_for_csp(
    db: Session, csp_id: int, include_closed: bool = False, proposed_only: bool = False
) -> list[Commitment]:
    """Open commitments by default; proposed_only lists the AI's un-reviewed suggestions instead."""
    q = select(Commitment).where(Commitment.csp_id == csp_id)
    if proposed_only:
        q = q.where(Commitment.status == CommitmentStatus.PROPOSED)
    elif not include_closed:
        q = q.where(Commitment.status == CommitmentStatus.OPEN)
    else:
        q = q.where(Commitment.status != CommitmentStatus.PROPOSED)
    q = q.order_by(
        Commitment.status,
        Commitment.due_date.is_(None),
        Commitment.due_date,
        Commitment.created_at.desc(),
    )
    return list(db.scalars(q).all())


def set_status(
    db: Session, commitment: Commitment, status: CommitmentStatus, actor: User
) -> Commitment:
    if status == CommitmentStatus.PROPOSED:
        raise ValueError("a commitment cannot be moved back to 'proposed'")
    was = commitment.status
    if was == CommitmentStatus.PROPOSED and status == CommitmentStatus.DONE:
        raise ValueError("accept a suggested commitment before marking it done")
    commitment.status = status
    commitment.done_at = datetime.now(timezone.utc) if status == CommitmentStatus.DONE else None
    if was == CommitmentStatus.PROPOSED and status == CommitmentStatus.OPEN:
        action = "commitment.accepted"
    elif was == CommitmentStatus.PROPOSED and status == CommitmentStatus.CANCELLED:
        action = "commitment.dismissed"
    else:
        action = f"commitment.{status.value}"
    audit.record(
        db, action=action, entity_type="commitment", entity_id=commitment.id,
        actor_id=actor.id, before={"status": was.value}, after={"status": status.value},
    )
    db.commit()
    return commitment


def add_manual(
    db: Session, *, csp: Csp, text: str, party: CommitmentParty, due_date: date | None, actor: User
) -> Commitment:
    c = Commitment(
        csp_id=csp.id,
        owner_user_id=csp.rm_user_id,
        text=text[:500],
        party=party,
        due_date=due_date,
        status=CommitmentStatus.OPEN,
        source="manual",
        source_kind=CommitmentSourceKind.RM_CSP,
        created_by=actor.id,
    )
    db.add(c)
    db.flush()
    audit.record(
        db, action="commitment.added", entity_type="commitment", entity_id=c.id,
        actor_id=actor.id, after={"csp_id": csp.id, "manual": True},
    )
    db.commit()
    return c


def apply_lifecycle(db: Session, now: datetime | None = None) -> dict:
    """Lifecycle rules for commitments - deliberately separate from the audio and transcript rules.

    * PROPOSED that nobody reviewed for commitment_proposal_expiry_days -> CANCELLED (audited as
      "proposal_expired"). An AI suggestion must not linger as a permanent to-do.
    * OPEN commitments NEVER expire: an open promise stays visible until a human closes it.
    * DONE / CANCELLED commitments are deleted commitment_closed_retention_days after they were closed
      (updated_at is the close time; an expired proposal's clock starts when it expired). Each deletion
      is audited with ids and status only - never the commitment text.
    """
    now = now or datetime.now(timezone.utc)
    expiry_cutoff = now - timedelta(days=settings.commitment_proposal_expiry_days)
    expired = 0
    for c in db.scalars(
        select(Commitment)
        .where(Commitment.status == CommitmentStatus.PROPOSED)
        .where(Commitment.created_at < expiry_cutoff)
    ).all():
        c.status = CommitmentStatus.CANCELLED
        audit.record(
            db, action="commitment.proposal_expired", entity_type="commitment", entity_id=c.id,
            before={"status": "proposed"},
            after={"status": "cancelled", "source_kind": c.source_kind.value,
                   "expiry_days": settings.commitment_proposal_expiry_days},
        )
        expired += 1
    db.flush()

    purge_cutoff = now - timedelta(days=settings.commitment_closed_retention_days)
    purged = 0
    for c in db.scalars(
        select(Commitment)
        .where(Commitment.status.in_([CommitmentStatus.DONE, CommitmentStatus.CANCELLED]))
        .where(Commitment.updated_at < purge_cutoff)
    ).all():
        audit.record(
            db, action="commitment.purged", entity_type="commitment", entity_id=c.id,
            after={"status": c.status.value, "source_kind": c.source_kind.value,
                   "retention_days": settings.commitment_closed_retention_days},
        )
        db.delete(c)
        purged += 1
    return {"proposals_expired": expired, "closed_purged": purged}
