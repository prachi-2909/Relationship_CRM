"""Dated facts about an official — birthday, joining date, promotions — each
carrying its own provenance. Only verified dates can trigger a moment.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .official import FieldVerification

_field_verif = SAEnum(
    FieldVerification, native_enum=False, length=16, name="official_date_verification"
)


class DateKind(str, enum.Enum):
    BIRTHDAY = "birthday"
    JOINED = "joined"
    PROMOTED = "promoted"


_kind = SAEnum(DateKind, native_enum=False, length=16, name="official_date_kind")


class OfficialDate(Base, TimestampMixin):
    __tablename__ = "official_dates"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[DateKind] = mapped_column(_kind, nullable=False, index=True)
    value: Mapped[date] = mapped_column(Date, nullable=False)
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

    official = relationship("Official", lazy="joined")
