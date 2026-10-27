"""Commitment tracking: turn a call's AI brief into discrete, trackable commitments.

Extraction is idempotent per call - re-running never duplicates. Party (ours/theirs) is inferred
from the wording; a due date is parsed when the text states one. The same code serves RM-KO and
DC-SBI calls, tagging each commitment with its source_kind so retention/permission/audit stay
separable.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.call_intelligence import CallSession
from ..models.commitment import (
    Commitment,
    CommitmentEvent,
    CommitmentParty,
    CommitmentSourceKind,
    CommitmentStatus,
)
from ..models.csp import Csp
from ..models.user import User
from . import audit
from .commitment_similarity import are_similar

settings = get_settings()

# The subject at the start of a line is the strongest signal of who owns the promise
# ("CSP to fix…" = theirs, "RM to update…" = ours).
_SUBJECT_THEIRS = re.compile(r"^\s*(the\s+)?(csp|operator|bank\s*mitra|official|they|he|she|customer)\b", re.I)
_SUBJECT_OURS = re.compile(r"^\s*(the\s+)?(rm|dc|data\s*collector|field\s*officer|relationship\s*manager|we|i|eko|our\s+team)\b", re.I)
# Fallback: any mention of either side anywhere in the text.
_OURS = re.compile(r"\b(we|our|i will|i'll|rm|dc|data collector|field officer|relationship manager|eko)\b", re.I)
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


# duplicate_review values
REVIEW_FLAGGED = "flagged"    # awaiting a human decision
REVIEW_SEPARATE = "separate"  # a human said: different commitment, keep both
REVIEW_MERGED = "merged"      # a human said: same commitment; this row was closed into merged_into_id


def _event(db: Session, c: Commitment, action: str, actor_id: int | None = None, **detail) -> None:
    """Append to the commitment's own history. Detail is ids/scalars only - never the commitment text."""
    db.add(CommitmentEvent(commitment_id=c.id, action=action, actor_id=actor_id, detail=detail or None))


def _delete_commitments(db: Session, commitments: list[Commitment]) -> None:
    """Delete commitments together with everything that points at them (no dangling duplicate links,
    no orphan history), independent of whether the database enforces foreign keys."""
    ids = [c.id for c in commitments]
    if not ids:
        return
    db.execute(
        update(Commitment).where(Commitment.possible_duplicate_of_id.in_(ids)).values(possible_duplicate_of_id=None)
    )
    db.execute(update(Commitment).where(Commitment.merged_into_id.in_(ids)).values(merged_into_id=None))
    db.execute(sa_delete(CommitmentEvent).where(CommitmentEvent.commitment_id.in_(ids)))
    for c in commitments:
        db.delete(c)
    db.flush()


def _flag_duplicates(db: Session, new: list[Commitment]) -> int:
    """Flag each new commitment that reads like an EARLIER one for the same CSP/official. This only
    records a suggestion for a human to review - it never merges, hides or drops anything. Matching is
    deliberately conservative (see commitment_similarity)."""
    flagged = 0
    for c in new:
        if c.csp_id is not None:
            scope = Commitment.csp_id == c.csp_id
        elif c.official_id is not None:
            scope = Commitment.official_id == c.official_id
        else:
            continue
        best: Commitment | None = None
        best_score = 0.0
        for other in db.scalars(
            select(Commitment)
            .where(scope)
            .where(Commitment.id < c.id)            # only ever flag the later one; the earlier is the original
            .where(Commitment.merged_into_id.is_(None))
        ).all():
            ok, score = are_similar(
                c.text, other.text,
                party_a=c.party.value, party_b=other.party.value,
                due_a=c.due_date, due_b=other.due_date,
            )
            if ok and (best is None or score > best_score):
                best, best_score = other, score
        if best is not None:
            c.possible_duplicate_of_id = best.id
            c.duplicate_review = REVIEW_FLAGGED
            _event(db, c, "possible_duplicate", of=best.id, score=round(best_score, 2))
            flagged += 1
    if flagged:
        db.flush()
    return flagged


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
    confirm flow). Hedged wording ("might", "will try", "discussed") is never extracted. A new record
    that reads like an earlier one for the same counterparty is FLAGGED as a possible duplicate for a
    human to review - never merged or dropped.

    Re-running refreshes this call's still-unreviewed proposals from the current brief (so a re-recorded
    brief replaces stale proposals) and never touches accepted/done/cancelled/reviewed ones or duplicates
    a text the call already has.
    """
    brief = brief if brief is not None else (call.analysis.analysis_json if call.analysis else None)
    if not brief:
        return []

    # Refresh: drop this call's proposals no human has acted on (a proposal a human already ruled
    # "separate" on is kept - they have spoken).
    _delete_commitments(
        db,
        list(db.scalars(
            select(Commitment)
            .where(Commitment.call_session_id == call.id)
            .where(Commitment.status == CommitmentStatus.PROPOSED)
            .where(or_(Commitment.duplicate_review.is_(None), Commitment.duplicate_review == REVIEW_FLAGGED))
        ).all()),
    )

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
        for c in created:
            _event(
                db, c, "proposed" if status == CommitmentStatus.PROPOSED else "approved_with_brief",
                call_id=call.id,
            )
        _flag_duplicates(db, created)
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
    return _list(db, Commitment.csp_id == csp_id, include_closed, proposed_only)


def list_for_official(
    db: Session, official_id: int, include_closed: bool = False, proposed_only: bool = False
) -> list[Commitment]:
    return _list(db, Commitment.official_id == official_id, include_closed, proposed_only)


def _list(db: Session, scope, include_closed: bool, proposed_only: bool) -> list[Commitment]:
    q = select(Commitment).where(scope).where(Commitment.merged_into_id.is_(None))
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


_OUTCOMES = (None, "fulfilled", "not_fulfilled")


def set_status(
    db: Session, commitment: Commitment, status: CommitmentStatus, actor: User, outcome: str | None = None
) -> Commitment:
    """Move a commitment between states. Every change is an EXPLICIT human action and is written to the
    commitment's own history. `outcome` ("fulfilled" / "not_fulfilled") records how it ended; nothing
    ever marks a commitment fulfilled on its own - not a later call, not an extraction."""
    if status == CommitmentStatus.PROPOSED:
        raise ValueError("a commitment cannot be moved back to 'proposed'")
    if outcome not in _OUTCOMES:
        raise ValueError("outcome must be 'fulfilled' or 'not_fulfilled'")
    was = commitment.status
    if was == CommitmentStatus.PROPOSED and status == CommitmentStatus.DONE:
        raise ValueError("accept a suggested commitment before marking it done")
    if commitment.merged_into_id is not None and status == CommitmentStatus.OPEN:
        raise ValueError("this commitment was merged into another one - reopen that one instead")
    commitment.status = status
    commitment.done_at = datetime.now(timezone.utc) if status == CommitmentStatus.DONE else None
    if was == CommitmentStatus.PROPOSED and status == CommitmentStatus.OPEN:
        action, event = "commitment.accepted", "accepted"
    elif was == CommitmentStatus.PROPOSED and status == CommitmentStatus.CANCELLED:
        action, event = "commitment.dismissed", "dismissed"
    elif was in (CommitmentStatus.DONE, CommitmentStatus.CANCELLED) and status == CommitmentStatus.OPEN:
        action, event = "commitment.reopened", "reopened"
    else:
        action, event = f"commitment.{status.value}", status.value
    audit.record(
        db, action=action, entity_type="commitment", entity_id=commitment.id,
        actor_id=actor.id, before={"status": was.value}, after={"status": status.value, "outcome": outcome},
    )
    _event(db, commitment, event, actor_id=actor.id, frm=was.value, to=status.value, outcome=outcome)
    db.commit()
    return commitment


def review_duplicate(db: Session, c: Commitment, decision: str, actor: User) -> Commitment:
    """A human's ruling on a flagged near-duplicate.

    * "merge"    - same commitment. THIS row is closed (cancelled) and linked to the earlier one. It is
                   KEPT, with its own owner, due date, source call and history, and the earlier
                   commitment is not edited: nothing is lost, and the survivor reports what was folded in.
    * "separate" - different commitment: both stay, and the flag is cleared for good.
    """
    if decision not in ("merge", "separate"):
        raise ValueError("decision must be 'merge' or 'separate'")
    if c.duplicate_review != REVIEW_FLAGGED or c.possible_duplicate_of_id is None:
        raise ValueError("this commitment is not flagged as a possible duplicate")
    if decision == "separate":
        c.duplicate_review = REVIEW_SEPARATE
        _event(db, c, "kept_separate", actor_id=actor.id, other=c.possible_duplicate_of_id)
        audit.record(
            db, action="commitment.kept_separate", entity_type="commitment", entity_id=c.id,
            actor_id=actor.id, after={"other": c.possible_duplicate_of_id},
        )
        db.commit()
        return c

    if c.status not in (CommitmentStatus.PROPOSED, CommitmentStatus.OPEN):
        raise ValueError("only a proposed or open commitment can be merged into another")
    target = db.get(Commitment, c.possible_duplicate_of_id)
    hops = 0
    while target is not None and target.merged_into_id is not None and hops < 5:   # follow earlier merges
        target = db.get(Commitment, target.merged_into_id)
        hops += 1
    if target is None or target.id == c.id:
        raise ValueError("the commitment this one duplicated no longer exists")
    was = c.status
    c.status = CommitmentStatus.CANCELLED
    c.done_at = None
    c.merged_into_id = target.id
    c.duplicate_review = REVIEW_MERGED
    _event(db, c, "merged", actor_id=actor.id, into=target.id, frm=was.value)
    _event(
        db, target, "absorbed_duplicate", actor_id=actor.id, source=c.id,
        due_date=c.due_date.isoformat() if c.due_date else None,
        owner_user_id=c.owner_user_id, call_session_id=c.call_session_id,
    )
    audit.record(
        db, action="commitment.merged", entity_type="commitment", entity_id=c.id,
        actor_id=actor.id, before={"status": was.value}, after={"into": target.id},
    )
    db.commit()
    return c


def history(db: Session, c: Commitment) -> list[dict]:
    """The commitment's own trail, oldest first - who proposed, accepted, dismissed, merged it, and when."""
    rows = db.scalars(
        select(CommitmentEvent).where(CommitmentEvent.commitment_id == c.id).order_by(CommitmentEvent.id)
    ).all()
    return [
        {"action": e.action, "at": e.created_at.isoformat() if e.created_at else None,
         "actor_id": e.actor_id, "detail": e.detail or {}}
        for e in rows
    ]


def commitment_dict(db: Session, c: Commitment) -> dict:
    """The one JSON shape for a commitment (web and Android both read it)."""
    d: dict = {
        "id": c.id,
        "text": c.text,
        "party": c.party.value,
        "due_date": c.due_date.isoformat() if c.due_date else None,
        "status": c.status.value,
        "source": c.source,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "source_call_id": c.call_session_id,
        "owner_user_id": c.owner_user_id,
    }
    if c.duplicate_review == REVIEW_FLAGGED and c.possible_duplicate_of is not None:
        o = c.possible_duplicate_of
        d["possible_duplicate"] = {
            "id": o.id, "text": o.text, "party": o.party.value, "status": o.status.value,
            "due_date": o.due_date.isoformat() if o.due_date else None, "source_call_id": o.call_session_id,
        }
    folded = db.scalars(select(Commitment).where(Commitment.merged_into_id == c.id).order_by(Commitment.id)).all()
    if folded:
        d["also_mentioned"] = [
            {"id": m.id, "due_date": m.due_date.isoformat() if m.due_date else None,
             "source_call_id": m.call_session_id, "owner_user_id": m.owner_user_id}
            for m in folded
        ]
    return d


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
    _event(db, c, "added", actor_id=actor.id)
    _flag_duplicates(db, [c])
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
      (updated_at is the close time; an expired proposal's clock starts when it expired), together with
      their history. Each deletion is audited with ids and status only - never the commitment text.
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
        _event(db, c, "expired", expiry_days=settings.commitment_proposal_expiry_days)
        audit.record(
            db, action="commitment.proposal_expired", entity_type="commitment", entity_id=c.id,
            before={"status": "proposed"},
            after={"status": "cancelled", "source_kind": c.source_kind.value,
                   "expiry_days": settings.commitment_proposal_expiry_days},
        )
        expired += 1
    db.flush()

    purge_cutoff = now - timedelta(days=settings.commitment_closed_retention_days)
    to_purge = list(db.scalars(
        select(Commitment)
        .where(Commitment.status.in_([CommitmentStatus.DONE, CommitmentStatus.CANCELLED]))
        .where(Commitment.updated_at < purge_cutoff)
    ).all())
    for c in to_purge:
        audit.record(
            db, action="commitment.purged", entity_type="commitment", entity_id=c.id,
            after={"status": c.status.value, "source_kind": c.source_kind.value,
                   "retention_days": settings.commitment_closed_retention_days},
        )
    _delete_commitments(db, to_purge)
    return {"proposals_expired": expired, "closed_purged": len(to_purge)}
