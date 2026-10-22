"""DC app presence: foreground/background heartbeats from the mobile app, and
an admin-only live status list. See services/presence.py for the "online" rule.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.session import UserSession
from ...models.user import Role, User
from ...schemas.presence import PresenceStatusOut
from ...security.deps import get_current_user, require_roles
from ...services import presence as presence_svc

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post("/heartbeat", status_code=204)
def heartbeat(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    presence_svc.record_heartbeat(actor)
    db.commit()


@router.post("/background", status_code=204)
def background(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    presence_svc.record_background(actor)
    db.commit()


@router.get("/status", response_model=list[PresenceStatusOut])
def status(db: Session = Depends(get_db), actor: User = Depends(require_roles(Role.ADMIN))):
    now = datetime.now(timezone.utc)
    logged_in_user_ids = set(
        db.scalars(
            select(UserSession.user_id).where(
                UserSession.revoked_at.is_(None), UserSession.expires_at > now
            )
        )
    )
    users = db.scalars(select(User).order_by(User.name)).all()
    return [
        PresenceStatusOut(
            user_id=u.id,
            name=u.name,
            email=u.email,
            role=u.role.value,
            is_logged_in=u.id in logged_in_user_ids,
            is_online=presence_svc.is_online(u),
            last_active_at=u.last_active_at.isoformat() if u.last_active_at else None,
        )
        for u in users
    ]
