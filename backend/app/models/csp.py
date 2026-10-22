"""Customer Service Points (CSPs) - the bank's last-mile agents, sourced from the
calling sheet and assigned to a Relationship Manager. Unlike SBI Officials (the
CRM's existing contacts), CSPs are the RM's own calling list: each has a primary
and an alternate mobile, a category, and the branch it operates under. Only active
CSPs are imported."""

import enum
from datetime import date

from sqlalchemy import Date
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class CspStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


_status = SAEnum(CspStatus, native_enum=False, length=16, name="csp_status")


class Csp(Base, TimestampMixin):
    __tablename__ = "csps"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The calling sheet's own CSP ID (e.g. "1A850247") - the stable key we upsert on.
    csp_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alternate_mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The Relationship Manager this CSP is assigned to. rm_name is always set (from the sheet);
    # rm_user_id links to the RM's user account when one exists (mapped by first name on import).
    rm_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    rm_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    branch_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lho: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[CspStatus] = mapped_column(_status, nullable=False, default=CspStatus.ACTIVE)

    # Relationship-building details (enriched from the KO full-details export, matched on CSP ID).
    # The daily calling-sheet sync never touches these, so they survive a re-sync.
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)  # birthday reminders
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    home_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # The date a birthday wish email was last sent, so the daily job never double-sends.
    last_birthday_wish_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    rm_user = relationship("User", lazy="joined")
