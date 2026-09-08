"""Organisation units — a self-referential tree."""

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class OrgUnitStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


_status = SAEnum(
    OrgUnitStatus, native_enum=False, length=16, name="org_unit_status"
)


class OrganizationUnit(Base, TimestampMixin):
    __tablename__ = "organization_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    type_code: Mapped[str] = mapped_column(
        ForeignKey("org_unit_types.code", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[OrgUnitStatus] = mapped_column(
        _status, nullable=False, default=OrgUnitStatus.ACTIVE
    )
    unit_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    parent: Mapped["OrganizationUnit | None"] = relationship(
        remote_side="OrganizationUnit.id", back_populates="children"
    )
    children: Mapped[list["OrganizationUnit"]] = relationship(
        back_populates="parent", order_by="OrganizationUnit.name"
    )
