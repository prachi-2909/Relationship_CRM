"""Customer Service Points (CSPs), grouped by their Relationship Manager.

Powers the CRM Organisation section's "CSP Network" view (RM-wise) and the RM's own
CSP calling list in the mobile app."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.call_intelligence import CallSession
from ...models.commitment import Commitment, CommitmentParty, CommitmentStatus
from ...models.csp import Csp, CspStatus
from ...models.user import Role, User
from ...schemas.call_intelligence import CallSessionDetail
from ...schemas.intelligence import CommitmentStatusUpdate, DuplicateDecision, FeedbackIn
from ...schemas.csp import CspByRmResponse, CspOut, CspProfileResponse, CspRmGroup
from ...security.deps import get_current_user, require_roles
from ...models.intelligence_feedback import SUBJECT_CSP
from ...services import commitments as commitments_svc
from ...services import intelligence_feedback as feedback_svc
from ...services import csp_sync
from ...services import precall

settings = get_settings()

router = APIRouter(prefix="/csps", tags=["csps"])

# The Organisation section is for office staff; a DC never sees the CSP network.
_VIEWERS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER, Role.APPROVER_VIEWER)
_ADMINS = require_roles(Role.ADMIN)


def _active_csps(db: Session):
    return db.scalars(
        select(Csp).where(Csp.status == CspStatus.ACTIVE).order_by(Csp.rm_name, Csp.name)
    ).all()


@router.get("/by-rm", response_model=CspByRmResponse)
def csps_by_rm(db: Session = Depends(get_db), _: User = Depends(_VIEWERS)):
    """Every active CSP, grouped by the RM it is assigned to - the CSP Network view."""
    groups: dict[str, CspRmGroup] = {}
    for csp in _active_csps(db):
        g = groups.get(csp.rm_name)
        if g is None:
            g = CspRmGroup(rm_name=csp.rm_name, rm_user_id=csp.rm_user_id, count=0, csps=[])
            groups[csp.rm_name] = g
        g.csps.append(CspOut.model_validate(csp))
        g.count += 1
    ordered = sorted(groups.values(), key=lambda x: x.rm_name.lower())
    return CspByRmResponse(groups=ordered, total=sum(g.count for g in ordered))


@router.get("/mine", response_model=list[CspOut])
def my_csps(db: Session = Depends(get_db), actor: User = Depends(_VIEWERS)):
    """The logged-in RM's own active CSPs (their calling list in the app). An admin/viewer
    with no CSPs of their own gets an empty list."""
    rows = db.scalars(
        select(Csp)
        .where(Csp.status == CspStatus.ACTIVE)
        .where(Csp.rm_user_id == actor.id)
        .order_by(Csp.name)
    ).all()
    return [CspOut.model_validate(c) for c in rows]


def _scoped_csp(db: Session, csp_pk: int, actor: User) -> Csp:
    """Fetch an active CSP, enforcing that an RM may only reach their own CSPs."""
    csp = db.get(Csp, csp_pk)
    if csp is None or csp.status != CspStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="CSP not found")
    if actor.role == Role.RELATIONSHIP_MANAGER and csp.rm_user_id != actor.id:
        raise HTTPException(status_code=404, detail="CSP not found")
    return csp


class CommitmentCreate(BaseModel):
    text: str
    party: str = "ours"      # ours | theirs | mutual
    due_date: date | None = None


def _scoped_csp_commitment(db: Session, commitment_id: int, actor: User) -> Commitment:
    """A commitment reachable through the CSP routes. It must belong to a CSP the actor may act on:
    one that belongs to an SBI official (no csp_id) is NOT reachable here - those have their own,
    DC-territory-scoped routes - so an RM can never touch a DC's official commitments."""
    c = db.get(Commitment, commitment_id)
    if c is None or c.csp_id is None:
        raise HTTPException(status_code=404, detail="Commitment not found")
    _scoped_csp(db, c.csp_id, actor)  # 404 unless the RM owns the CSP (admins pass)
    return c


@router.get("/{csp_pk}/pre-call")
def csp_pre_call(csp_pk: int, db: Session = Depends(get_db), actor: User = Depends(_VIEWERS)):
    """Pre-Call Intelligence for one CSP: open commitments, relationship memory (built from retained
    briefs), the last conversation, current slab status and suggested talking points - everything the
    RM should see before dialling. RM sees only their own CSPs."""
    csp = _scoped_csp(db, csp_pk, actor)
    return precall.build_for_csp(db, csp, actor)


@router.post("/{csp_pk}/feedback")
def csp_feedback(
    csp_pk: int, payload: FeedbackIn, db: Session = Depends(get_db), actor: User = Depends(_VIEWERS),
):
    """Say whether a talking point for this CSP was useful. RM only for their own CSP (admin any); the
    suggestion is checked against what the server generates now, so nothing can be forged."""
    if actor.role not in (Role.ADMIN, Role.RELATIONSHIP_MANAGER):
        raise HTTPException(status_code=403, detail="Not allowed to give feedback")
    csp = _scoped_csp(db, csp_pk, actor)
    try:
        row = feedback_svc.submit(
            db, actor, SUBJECT_CSP, csp.id, payload.target_type, payload.key, payload.verdict,
            payload.note, precall.items_for_csp(db, csp),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "verdict": row.verdict}


@router.get("/{csp_pk}/commitments")
def csp_commitments(
    csp_pk: int, include_closed: bool = False,
    db: Session = Depends(get_db), actor: User = Depends(_VIEWERS),
):
    """Tracked commitments for a CSP (open by default), freshly synced from the call briefs."""
    csp = _scoped_csp(db, csp_pk, actor)
    items = commitments_svc.list_for_csp(db, csp.id, include_closed=include_closed)
    proposed = commitments_svc.list_for_csp(db, csp.id, proposed_only=True)
    return {
        "items": [commitments_svc.commitment_dict(db, c) for c in items], "total": len(items),
        "proposed": [commitments_svc.commitment_dict(db, c) for c in proposed],
    }


@router.post("/{csp_pk}/commitments")
def add_csp_commitment(
    csp_pk: int, payload: CommitmentCreate,
    db: Session = Depends(get_db), actor: User = Depends(_VIEWERS),
):
    """Add a commitment manually (e.g. agreed on a call that had no recording)."""
    if actor.role not in (Role.ADMIN, Role.RELATIONSHIP_MANAGER):
        raise HTTPException(status_code=403, detail="Not allowed to add commitments")
    csp = _scoped_csp(db, csp_pk, actor)
    try:
        party = CommitmentParty(payload.party)
    except ValueError:
        party = CommitmentParty.OURS
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Commitment text is required")
    c = commitments_svc.add_manual(
        db, csp=csp, text=text, party=party, due_date=payload.due_date, actor=actor
    )
    return commitments_svc.commitment_dict(db, c)


@router.post("/commitments/{commitment_id}/status")
def update_commitment_status(
    commitment_id: int, payload: CommitmentStatusUpdate,
    db: Session = Depends(get_db), actor: User = Depends(_VIEWERS),
):
    """Mark a commitment done / cancelled / reopened. RM may only touch their own CSP's commitments."""
    if actor.role not in (Role.ADMIN, Role.RELATIONSHIP_MANAGER):
        raise HTTPException(status_code=403, detail="Not allowed to update commitments")
    c = _scoped_csp_commitment(db, commitment_id, actor)
    try:
        status = CommitmentStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status")
    if status == CommitmentStatus.PROPOSED:
        raise HTTPException(status_code=400, detail="Invalid status")
    try:
        commitments_svc.set_status(db, c, status, actor, outcome=payload.outcome)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return commitments_svc.commitment_dict(db, c)


@router.post("/commitments/{commitment_id}/duplicate")
def review_commitment_duplicate(
    commitment_id: int, payload: DuplicateDecision,
    db: Session = Depends(get_db), actor: User = Depends(_VIEWERS),
):
    """Rule on a flagged near-duplicate: "merge" (same commitment - this one is closed into the earlier
    one, nothing is deleted) or "separate" (different - keep both). A human always decides."""
    if actor.role not in (Role.ADMIN, Role.RELATIONSHIP_MANAGER):
        raise HTTPException(status_code=403, detail="Not allowed to update commitments")
    c = _scoped_csp_commitment(db, commitment_id, actor)
    try:
        commitments_svc.review_duplicate(db, c, payload.decision, actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return commitments_svc.commitment_dict(db, c)


@router.get("/commitments/{commitment_id}/history")
def commitment_history(
    commitment_id: int, db: Session = Depends(get_db), actor: User = Depends(_VIEWERS),
):
    """The commitment's own trail: proposed, accepted / dismissed, done, merged ..., with who and when."""
    c = _scoped_csp_commitment(db, commitment_id, actor)
    return {"commitment_id": c.id, "events": commitments_svc.history(db, c)}


@router.get("/{csp_pk}/profile", response_model=CspProfileResponse)
def csp_profile(
    csp_pk: int, db: Session = Depends(get_db), actor: User = Depends(_VIEWERS)
) -> CspProfileResponse:
    """One Kiosk Operator plus every call had with them (newest first) - the KO's
    relationship profile. An RM may open only their own CSPs; admins/viewers see any."""
    csp = db.get(Csp, csp_pk)
    if csp is None or csp.status != CspStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="CSP not found")
    if actor.role == Role.RELATIONSHIP_MANAGER and csp.rm_user_id != actor.id:
        raise HTTPException(status_code=404, detail="CSP not found")

    calls = db.scalars(
        select(CallSession)
        .where(CallSession.csp_id == csp.id)
        .order_by(CallSession.started_at.desc())
    ).all()
    return CspProfileResponse(
        csp=CspOut.model_validate(csp),
        calls=[CallSessionDetail.of(c) for c in calls],
        calls_total=len(calls),
    )


@router.post("/sync")
def sync_now(db: Session = Depends(get_db), _: User = Depends(_ADMINS)):
    """Re-sync CSPs from the live calling sheet on demand (the same reconcile the 8 PM job runs)."""
    summary = csp_sync.sync_csps_from_sheet(db)
    db.commit()
    return summary


@router.get("/birthdays/today")
def birthdays_today(db: Session = Depends(get_db), _: User = Depends(_VIEWERS)):
    """CSPs whose birthday is today (with an email on file) - a preview of who the wish job covers."""
    from datetime import date

    from ...services import birthdays

    today = date.today()
    rows = birthdays.todays_birthday_csps(db)
    return {
        "count": len(rows),
        "csps": [
            {"csp_id": c.csp_id, "name": c.name, "email": c.email, "rm_name": c.rm_name,
             "already_wished_today": c.last_birthday_wish_on == today}
            for c in rows
        ],
    }


@router.get("/birthday-wishes/preview")
def birthday_wishes_preview(db: Session = Depends(get_db), actor: User = Depends(_VIEWERS)):
    """Read-only preview of the exact personalised, bilingual birthday messages that WOULD be sent -
    today's sendable wishes plus the next 7 days coming up. Never sends anything. An RM sees only
    their own CSPs; admins/viewers see all."""
    from datetime import date

    from ...services import birthdays
    from ...services import email as email_svc

    today = date.today()
    is_rm = actor.role == Role.RELATIONSHIP_MANAGER

    def mine(csp: Csp) -> bool:
        return not is_rm or csp.rm_user_id == actor.id

    def draft_for(csp: Csp, in_days: int) -> dict:
        return {
            "id": csp.id, "csp_id": csp.csp_id, "name": csp.name, "email": csp.email,
            "rm_name": csp.rm_name, "in_days": in_days,
            "already_sent": csp.last_birthday_wish_on == today,
            **birthdays.personalize(db, csp),
        }

    # Include already-wished CSPs too (shown as "Sent" in the UI) so the day's list stays complete.
    todays = [c for c in birthdays.todays_birthday_csps(db, today) if mine(c)]
    upcoming = [(c, d) for c, d in birthdays.upcoming_birthday_csps(db, days=30, today=today) if mine(c)]

    return {
        "date": today.isoformat(),
        "gmail_configured": email_svc.is_configured(),
        "draft_only": settings.email_draft_only,
        "wishes_enabled": settings.csp_birthday_wishes_enabled,
        "today": [draft_for(c, 0) for c in todays],
        "upcoming": [draft_for(c, d) for c, d in upcoming],
    }


@router.get("/birthday-wishes/sent")
def birthday_wishes_sent(
    limit: int = 50, db: Session = Depends(get_db), actor: User = Depends(_VIEWERS)
):
    """Log of birthday wishes already sent - who got one, on which date and email, and the exact
    message - so the team can see what went out. Newest first. An RM sees only their own CSPs."""
    from ...services import birthdays

    is_rm = actor.role == Role.RELATIONSHIP_MANAGER
    rows = db.scalars(
        select(Csp)
        .where(Csp.status == CspStatus.ACTIVE)
        .where(Csp.last_birthday_wish_on.is_not(None))
        .order_by(Csp.last_birthday_wish_on.desc(), Csp.name)
    ).all()
    items = []
    for c in rows:
        if is_rm and c.rm_user_id != actor.id:
            continue
        draft = birthdays.personalize(db, c)
        items.append({
            "csp_id": c.csp_id, "name": c.name, "email": c.email, "rm_name": c.rm_name,
            "sent_on": c.last_birthday_wish_on.isoformat(),
            "subject": draft["subject"], "message": draft["message"],
        })
        if len(items) >= limit:
            break
    return {"items": items, "total": len(items)}


@router.post("/{csp_pk}/birthday-wish")
def send_one_birthday_wish(
    csp_pk: int, db: Session = Depends(get_db), actor: User = Depends(_VIEWERS)
):
    """Send ONE CSP's birthday wish right now, from the Birthday Wishes page's Send button. This is an
    explicit human action, so it sends for real even while the automatic daily job is off / in
    draft-only mode. Idempotent: a CSP already wished today is not re-sent. An RM may send only to
    their own CSPs."""
    from datetime import date

    from ...services import audit
    from ...services import birthdays
    from ...services import email as email_svc

    if actor.role not in (Role.ADMIN, Role.RELATIONSHIP_MANAGER):
        raise HTTPException(status_code=403, detail="You are not allowed to send wishes")
    csp = db.get(Csp, csp_pk)
    if csp is None or csp.status != CspStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="CSP not found")
    if actor.role == Role.RELATIONSHIP_MANAGER and csp.rm_user_id != actor.id:
        raise HTTPException(status_code=404, detail="CSP not found")
    if not (csp.email and "@" in csp.email):
        raise HTTPException(status_code=400, detail="This CSP has no email on file")
    if not email_svc.is_configured():
        raise HTTPException(status_code=400, detail="Gmail sender is not configured")

    today = date.today()
    if csp.last_birthday_wish_on == today:
        return {"ok": True, "already_sent": True, "sent_to": csp.email}

    draft = birthdays.personalize(db, csp)
    result = email_svc.send_email(
        to=csp.email, name=birthdays._first_name(csp.name),
        message=draft["message"], subject=draft["subject"],
    )
    if not result.ok:
        raise HTTPException(status_code=502, detail=f"Send failed: {result.error}")
    csp.last_birthday_wish_on = today
    audit.record(
        db, action="csp.birthday_wish_sent", entity_type="csp", entity_id=csp.id,
        actor_id=actor.id, after={"email": csp.email},
    )
    db.commit()
    return {"ok": True, "sent_to": csp.email}


@router.post("/birthday-wishes")
def send_birthday_wishes_now(
    dry_run: bool = False, db: Session = Depends(get_db), _: User = Depends(_ADMINS)
):
    """Send today's CSP birthday wishes on demand. dry_run=true previews recipients without sending."""
    from ...services import birthdays

    return birthdays.send_birthday_wishes(db, dry_run=dry_run)
