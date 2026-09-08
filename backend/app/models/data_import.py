"""Bulk import of officials from Excel / CSV: staged, previewed, then committed."""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class ImportStatus(str, enum.Enum):
    PENDING = "pending"       # parsed + resolved, waiting for a human to commit
    COMMITTED = "committed"
    CANCELLED = "cancelled"


class RowAction(str, enum.Enum):
    CREATE = "create"
    MERGE = "merge"
    SKIP = "skip"


_status = SAEnum(ImportStatus, native_enum=False, length=16, name="data_import_status")
_action = SAEnum(RowAction, native_enum=False, length=8, name="import_row_action")


class DataImport(Base, TimestampMixin):
    __tablename__ = "data_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        _status, nullable=False, default=ImportStatus.PENDING, index=True
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    rows: Mapped[list["ImportRow"]] = relationship(
        back_populates="data_import",
        cascade="all, delete-orphan",
        order_by="ImportRow.row_number",
    )


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(
        ForeignKey("data_imports.id", ondelete="CASCADE"), index=True, nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized: Mapped[dict] = mapped_column(JSON, nullable=False)
    resolved_official_id: Mapped[int | None] = mapped_column(
        ForeignKey("officials.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[RowAction] = mapped_column(_action, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)

    data_import: Mapped[DataImport] = relationship(back_populates="rows")
