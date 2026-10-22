"""Shared organisation-unit hierarchy helpers - used by the units API itself
and by anything that needs to reason about a subtree (DC territory scoping,
today).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.organization_unit import OrganizationUnit


def descendant_ids(db: Session, root_id: int) -> set[int]:
    """Every unit under root_id, not including root_id itself."""
    seen: set[int] = set()
    frontier = [root_id]
    while frontier:
        rows = db.scalars(
            select(OrganizationUnit.id).where(OrganizationUnit.parent_id.in_(frontier))
        ).all()
        new = [r for r in rows if r not in seen]
        seen.update(new)
        frontier = new
    return seen
