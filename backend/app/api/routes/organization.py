"""Organisation units and their configurable types."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.official import Official, OfficialStatus
from ...models.organization_unit import OrganizationUnit, OrgUnitStatus
from ...models.org_unit_type import OrgUnitType
from ...models.user import Role, User
from ...schemas.organization import (
    UnitCreate,
    UnitOut,
    UnitTreeNode,
    UnitTypeCreate,
    UnitTypeOut,
    UnitUpdate,
)
from ...security.deps import get_current_user, require_roles
from ...services import audit

router = APIRouter(prefix="/organization", tags=["organization"])


# --- unit types -------------------------------------------------------------


@router.get("/unit-types", response_model=list[UnitTypeOut])
def list_unit_types(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(OrgUnitType).order_by(OrgUnitType.rank, OrgUnitType.code)
    if not include_inactive:
        stmt = stmt.where(OrgUnitType.active.is_(True))
    return list(db.scalars(stmt))


@router.post("/unit-types", response_model=UnitTypeOut, status_code=status.HTTP_201_CREATED)
def create_unit_type(
    payload: UnitTypeCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    code = payload.code.strip().upper()
    if db.scalar(select(OrgUnitType).where(OrgUnitType.code == code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Type code already exists")
    unit_type = OrgUnitType(code=code, label=payload.label, rank=payload.rank, active=True)
    db.add(unit_type)
    db.flush()
    audit.record(
        db,
        action="org_unit_type.create",
        entity_type="org_unit_type",
        entity_id=code,
        actor_id=actor.id,
        after={"code": code, "label": unit_type.label},
    )
    db.commit()
    db.refresh(unit_type)
    return unit_type


# --- units ----------------------------------------------------------------


def _require_active_type(db: Session, type_code: str) -> OrgUnitType:
    unit_type = db.scalar(select(OrgUnitType).where(OrgUnitType.code == type_code))
    if unit_type is None or not unit_type.active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown unit type")
    return unit_type


def _validate_hierarchy(db: Session, type_code: str, parent_id: int | None) -> None:
    """A unit's type must sit strictly below its parent's type in `rank`
    (lower rank = higher in the org - Corporate Centre 10, Branch 50, etc.).
    A level may be skipped (e.g. a Branch directly under an LHO), but the
    direction can't be wrong, and only the topmost type may be rootless."""
    # OrgUnitType's primary key is `id`, not `code` - db.get() needs a lookup
    # by the unique `code` column instead.
    child_type = db.scalar(select(OrgUnitType).where(OrgUnitType.code == type_code))
    if child_type is None:  # already 422'd by _require_active_type upstream
        return

    if parent_id is None:
        top_rank = db.scalar(
            select(func.min(OrgUnitType.rank)).where(OrgUnitType.active.is_(True))
        )
        if child_type.rank != top_rank:
            top_type = db.scalar(
                select(OrgUnitType).where(OrgUnitType.rank == top_rank)
            )
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Only a {top_type.label if top_type else 'top-level'} unit can be "
                "created without a parent",
            )
        return

    parent = db.get(OrganizationUnit, parent_id)
    if parent is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Parent unit not found")
    parent_type = db.scalar(select(OrgUnitType).where(OrgUnitType.code == parent.type_code))
    if parent_type is not None and child_type.rank <= parent_type.rank:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"A {child_type.label} cannot be placed under a {parent_type.label} - "
            f"{parent_type.label} is not above {child_type.label} in the hierarchy",
        )


def _descendant_ids(db: Session, root_id: int) -> set[int]:
    seen: set[int] = set()
    frontier = [root_id]
    while frontier:
        rows = db.scalars(
            select(OrganizationUnit.id).where(
                OrganizationUnit.parent_id.in_(frontier)
            )
        ).all()
        new = [r for r in rows if r not in seen]
        seen.update(new)
        frontier = new
    return seen


@router.get("/units", response_model=list[UnitOut])
def list_units(
    status_filter: OrgUnitStatus | None = Query(default=None, alias="status"),
    type_code: str | None = None,
    parent_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(OrganizationUnit).order_by(OrganizationUnit.name)
    if status_filter is not None:
        stmt = stmt.where(OrganizationUnit.status == status_filter)
    if type_code is not None:
        stmt = stmt.where(OrganizationUnit.type_code == type_code)
    if parent_id is not None:
        stmt = stmt.where(OrganizationUnit.parent_id == parent_id)
    return list(db.scalars(stmt))


@router.get("/units/tree", response_model=list[UnitTreeNode])
def unit_tree(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(OrganizationUnit).order_by(OrganizationUnit.name)
    if not include_archived:
        stmt = stmt.where(OrganizationUnit.status == OrgUnitStatus.ACTIVE)
    units = list(db.scalars(stmt))

    nodes: dict[int, UnitTreeNode] = {
        u.id: UnitTreeNode(**UnitOut.model_validate(u).model_dump(), children=[])
        for u in units
    }
    roots: list[UnitTreeNode] = []
    for unit in units:
        node = nodes[unit.id]
        parent = nodes.get(unit.parent_id) if unit.parent_id else None
        if parent is not None:
            parent.children.append(node)
        else:
            roots.append(node)
    return roots


@router.get("/units/{unit_id}", response_model=UnitOut)
def get_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    unit = db.get(OrganizationUnit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unit not found")
    return unit


@router.post("/units", response_model=UnitOut, status_code=status.HTTP_201_CREATED)
def create_unit(
    payload: UnitCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    _require_active_type(db, payload.type_code)
    _validate_hierarchy(db, payload.type_code, payload.parent_id)

    unit = OrganizationUnit(
        name=payload.name,
        type_code=payload.type_code,
        parent_id=payload.parent_id,
        location=payload.location,
        department=payload.department,
        unit_metadata=payload.metadata,
        status=OrgUnitStatus.ACTIVE,
    )
    db.add(unit)
    db.flush()
    audit.record(
        db,
        action="org_unit.create",
        entity_type="org_unit",
        entity_id=unit.id,
        actor_id=actor.id,
        after={"name": unit.name, "type_code": unit.type_code, "parent_id": unit.parent_id},
    )
    db.commit()
    db.refresh(unit)
    return unit


@router.patch("/units/{unit_id}", response_model=UnitOut)
def update_unit(
    unit_id: int,
    payload: UnitUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    unit = db.get(OrganizationUnit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unit not found")

    data = payload.model_dump(exclude_unset=True)

    if "type_code" in data and data["type_code"] is not None:
        _require_active_type(db, data["type_code"])

    if "parent_id" in data and data["parent_id"] is not None:
        new_parent = data["parent_id"]
        if new_parent == unit.id or new_parent in _descendant_ids(db, unit.id):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Cannot move a unit under itself"
            )

    if "type_code" in data or "parent_id" in data:
        _validate_hierarchy(
            db,
            data.get("type_code", unit.type_code),
            data["parent_id"] if "parent_id" in data else unit.parent_id,
        )

    if data.get("status") == OrgUnitStatus.ARCHIVED:
        active_children = db.scalar(
            select(OrganizationUnit.id)
            .where(OrganizationUnit.parent_id == unit.id)
            .where(OrganizationUnit.status == OrgUnitStatus.ACTIVE)
        )
        active_officials = db.scalar(
            select(Official.id)
            .where(Official.organization_unit_id == unit.id)
            .where(Official.status == OfficialStatus.ACTIVE)
        )
        if active_children or active_officials:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Reassign or archive child units and officials first",
            )

    before = {
        "name": unit.name,
        "type_code": unit.type_code,
        "parent_id": unit.parent_id,
        "status": unit.status.value,
    }
    for key in ("name", "type_code", "parent_id", "location", "department", "status"):
        if key in data:
            setattr(unit, key, data[key])
    if "metadata" in data:
        unit.unit_metadata = data["metadata"]

    audit.record(
        db,
        action="org_unit.update",
        entity_type="org_unit",
        entity_id=unit.id,
        actor_id=actor.id,
        before=before,
        after={
            "name": unit.name,
            "type_code": unit.type_code,
            "parent_id": unit.parent_id,
            "status": unit.status.value,
        },
    )
    db.commit()
    db.refresh(unit)
    return unit
