"""Customer Service Points (CSPs), grouped by their Relationship Manager.

Powers the CRM Organisation section's "CSP Network" view (RM-wise) and the RM's own
CSP calling list in the mobile app."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.call_intelligence import CallSession
from ...models.csp import Csp, CspStatus
from ...models.user import Role, User
from ...schemas.call_intelligence import CallSessionDetail
from ...schemas.csp import CspByRmResponse, CspOut, CspProfileResponse, CspRmGroup
from ...security.deps import get_current_user, require_roles
from ...services import csp_sync

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


@router.post("/birthday-wishes")
def send_birthday_wishes_now(
    dry_run: bool = False, db: Session = Depends(get_db), _: User = Depends(_ADMINS)
):
    """Send today's CSP birthday wishes on demand. dry_run=true previews recipients without sending."""
    from ...services import birthdays

    return birthdays.send_birthday_wishes(db, dry_run=dry_run)
