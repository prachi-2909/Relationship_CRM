"""A DC's effective scope: every organisation unit their territory covers,
including descendants, and the officials that live under those units. Used
to restrict a DC's official search/read/write to only their own area.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.dc_territory import DCTerritory
from ..models.official import Official
from ..models.organization_unit import OrganizationUnit
from .organization import descendant_ids


def scoped_unit_ids(db: Session, dc_user_id: int) -> set[int]:
    assigned = set(
        db.scalars(select(DCTerritory.organization_unit_id).where(DCTerritory.dc_user_id == dc_user_id))
    )
    result = set(assigned)
    for unit_id in assigned:
        result |= descendant_ids(db, unit_id)
    return result


def ancestor_ids(db: Session, unit_id: int) -> set[int]:
    result: set[int] = set()
    unit = db.get(OrganizationUnit, unit_id)
    while unit is not None and unit.parent_id is not None:
        result.add(unit.parent_id)
        unit = db.get(OrganizationUnit, unit.parent_id)
    return result


def visible_unit_ids(db: Session, dc_user_id: int) -> set[int]:
    """scoped_unit_ids, plus the ANCESTORS of the DC's assigned units - an
    official recorded once for a whole RBO/AO (e.g. its Field Investigator)
    is attached at that RBO/AO unit, not at each branch under it, so a DC
    whose territory is one of those branches still needs to see it. Read-only:
    never used to decide where a DC may create/move an official (that stays
    on scoped_unit_ids/can_access_unit, which is exact-or-descendant only)."""
    assigned = set(
        db.scalars(select(DCTerritory.organization_unit_id).where(DCTerritory.dc_user_id == dc_user_id))
    )
    result = scoped_unit_ids(db, dc_user_id)
    for unit_id in assigned:
        result |= ancestor_ids(db, unit_id)
    return result


def can_access_official(db: Session, dc_user_id: int, official: Official) -> bool:
    if official.organization_unit_id is None:
        return False
    return official.organization_unit_id in visible_unit_ids(db, dc_user_id)


def can_access_unit(db: Session, dc_user_id: int, unit_id: int) -> bool:
    return unit_id in scoped_unit_ids(db, dc_user_id)
