"""Customer Service Points (CSPs), grouped by their Relationship Manager.

Powers the CRM Organisation section's "CSP Network" view (RM-wise) and the RM's own
CSP calling list in the mobile app."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.call_intelligence import CallSession
from ...models.csp import Csp, CspStatus
from ...models.user import Role, User
from ...schemas.call_intelligence import CallSessionDetail
from ...schemas.csp import CspByRmResponse, CspOut, CspProfileResponse, CspRmGroup
from ...security.deps import get_current_user, require_roles
from ...services import csp_sync

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
