"""DC territory assignment (admin-managed) and a DC's own profile view."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.call_intelligence import CallSession, CallSessionStatus
from ...models.dc_territory import DCTerritory
from ...models.official import Official
from ...models.organization_unit import OrganizationUnit
from ...models.user import Role, User
from ...schemas.dc_territory import DcProfile, TerritoryAssign, TerritoryOut
from ...security.deps import get_current_user, require_roles
from ...services import audit
from ...services.dc_territory import ancestor_ids

router = APIRouter(tags=["dc-territory"])


def _out(row: DCTerritory) -> TerritoryOut:
    return TerritoryOut(
        id=row.id,
        dc_user_id=row.dc_user_id,
        dc_user_name=row.dc_user.name,
        organization_unit_id=row.organization_unit_id,
        organization_unit_name=row.organization_unit.name,
        organization_unit_type=row.organization_unit.type_code,
        assigned_at=row.created_at,
    )


@router.get("/dc-territories", response_model=list[TerritoryOut])
def list_territories(
    dc_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Admin: any DC's territory. A DC: only their own. An RM has no DC territory, so gets an
    empty list (the shared app calls this on login for every role)."""
    if actor.role is Role.DC:
        dc_user_id = actor.id
    elif actor.role is Role.RELATIONSHIP_MANAGER:
        dc_user_id = actor.id  # RMs have no territory rows -> empty result
    elif actor.role is not Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    stmt = select(DCTerritory)
    if dc_user_id is not None:
        stmt = stmt.where(DCTerritory.dc_user_id == dc_user_id)
    rows = db.scalars(stmt.order_by(DCTerritory.id)).all()
    return [_out(r) for r in rows]


@router.post("/dc-territories", response_model=TerritoryOut, status_code=status.HTTP_201_CREATED)
def assign_territory(
    payload: TerritoryAssign,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    dc = db.get(User, payload.dc_user_id)
    if dc is None or dc.role is not Role.DC:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Not a DC user")
    unit = db.get(OrganizationUnit, payload.organization_unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unit not found")
    existing = db.scalar(
        select(DCTerritory)
        .where(DCTerritory.dc_user_id == dc.id)
        .where(DCTerritory.organization_unit_id == unit.id)
    )
    if existing is not None:
        return _out(existing)

    row = DCTerritory(dc_user_id=dc.id, organization_unit_id=unit.id, assigned_by=actor.id)
    db.add(row)
    db.flush()
    audit.record(
        db, action="dc_territory.assign", entity_type="dc_territory", entity_id=row.id,
        actor_id=actor.id, after={"dc_user_id": dc.id, "organization_unit_id": unit.id},
    )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/dc-territories/{territory_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_territory(
    territory_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    row = db.get(DCTerritory, territory_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Territory assignment not found")
    audit.record(
        db, action="dc_territory.remove", entity_type="dc_territory", entity_id=row.id,
        actor_id=actor.id, before={"dc_user_id": row.dc_user_id, "organization_unit_id": row.organization_unit_id},
    )
    db.delete(row)
    db.commit()


@router.get("/dc/profile", response_model=DcProfile)
def dc_profile(
    dc_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """A DC's own profile (name, territory, activity). Admin can view any
    DC's profile by passing dc_user_id."""
    if actor.role is Role.DC:
        target_id = actor.id
    elif actor.role is Role.RELATIONSHIP_MANAGER:
        target_id = actor.id  # an RM views their own profile; they just have no DC territory
    elif actor.role is Role.ADMIN and dc_user_id is not None:
        target_id = dc_user_id
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    dc = db.get(User, target_id)
    if dc is None or dc.role not in (Role.DC, Role.RELATIONSHIP_MANAGER):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DC not found")

    territory_rows = db.scalars(select(DCTerritory).where(DCTerritory.dc_user_id == dc.id)).all()
    direct_unit_ids = {r.organization_unit_id for r in territory_rows}
    territory = [_out(r) for r in territory_rows]

    covered_ancestor_ids: set[int] = set()
    for unit_id in direct_unit_ids:
        covered_ancestor_ids |= ancestor_ids(db, unit_id)
    covered_ancestor_ids -= direct_unit_ids
    for ancestor_id in covered_ancestor_ids:
        has_officials = db.scalar(
            select(Official.id).where(Official.organization_unit_id == ancestor_id)
        ) is not None
        if not has_officials:
            continue
        unit = db.get(OrganizationUnit, ancestor_id)
        if unit is None:
            continue
        territory.append(TerritoryOut(
            dc_user_id=dc.id, dc_user_name=dc.name,
            organization_unit_id=unit.id, organization_unit_name=unit.name,
            organization_unit_type=unit.type_code, is_direct=False,
        ))

    pending = db.query(CallSession).filter(
        CallSession.dc_user_id == dc.id,
        CallSession.processing_status.in_([CallSessionStatus.INITIATED, CallSessionStatus.REVIEW_REQUIRED]),
    ).count()
    logged = db.query(CallSession).filter(
        CallSession.dc_user_id == dc.id,
        CallSession.processing_status == CallSessionStatus.CRM_LOGGED,
    ).count()

    return DcProfile(
        id=dc.id, name=dc.name, email=dc.email, status=dc.status.value,
        territory=territory,
        pending_calls=pending, logged_interactions=logged,
    )
