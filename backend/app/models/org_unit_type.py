"""Configurable organisation-unit types.

Seeded with a generic hierarchy (Head Office, Regional Office, Zonal Office,
Area Office, Branch) but editable as data — no application logic branches on a
specific code.
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class OrgUnitType(Base, TimestampMixin):
    __tablename__ = "org_unit_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # A hint for ordering pick-lists and suggesting nesting; not enforced.
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
