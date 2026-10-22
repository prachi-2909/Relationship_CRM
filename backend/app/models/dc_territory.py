"""A DC's assigned territory: which organisation units (any level - AO, RBO,
or a single Branch) they cover. Access to Officials is scoped to a DC's
territory plus every descendant of each assigned unit - assigning a DC to an
AO implicitly covers every RBO/Branch under it, no need to list each one.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class DCTerritory(Base, TimestampMixin):
    __tablename__ = "dc_territories"
    __table_args__ = (UniqueConstraint("dc_user_id", "organization_unit_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dc_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_unit_id: Mapped[int] = mapped_column(
        ForeignKey("organization_units.id", ondelete="CASCADE"), index=True, nullable=False
    )
    assigned_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    dc_user = relationship("User", foreign_keys=[dc_user_id], lazy="joined")
    organization_unit = relationship("OrganizationUnit", lazy="joined")
