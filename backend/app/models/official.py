"""Officials and per-field provenance."""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class OfficialStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    PARTIALLY_VERIFIED = "partially_verified"
    VERIFIED = "verified"


class FieldVerification(str, enum.Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


# Enriched fields that carry provenance. Kept as a constant so the API and the
# roll-up computation agree on what "fully verified" means.
PROVENANCED_FIELDS: tuple[str, ...] = (
    "designation",
    "department",
    "level",
    "location",
    "organization_unit_id",
)

_status = SAEnum(OfficialStatus, native_enum=False, length=16, name="official_status")
_verif = SAEnum(
    VerificationStatus, native_enum=False, length=24, name="official_verification"
)
_field_verif = SAEnum(
    FieldVerification, native_enum=False, length=16, name="field_verification"
)


class Official(Base, TimestampMixin):
    __tablename__ = "officials"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    level: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organization_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[OfficialStatus] = mapped_column(
        _status, nullable=False, default=OfficialStatus.ACTIVE
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        _verif, nullable=False, default=VerificationStatus.UNVERIFIED, index=True
    )

    organization_unit = relationship("OrganizationUnit", lazy="joined")
    field_provenance: Mapped[list["OfficialFieldProvenance"]] = relationship(
        back_populates="official",
        cascade="all, delete-orphan",
        order_by="OfficialFieldProvenance.field",
    )


class OfficialFieldProvenance(Base, TimestampMixin):
    __tablename__ = "official_field_provenance"
    __table_args__ = (
        UniqueConstraint("official_id", "field", name="uq_official_field"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[FieldVerification] = mapped_column(
        _field_verif, nullable=False, default=FieldVerification.UNVERIFIED
    )
    verified_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    official: Mapped[Official] = relationship(back_populates="field_provenance")
