"""Media-deletion outbox.

Every deletion of a stored media file is first recorded here IN THE SAME TRANSACTION that removes the
database row pointing at it, and only then carried out. That gives three guarantees the old
fire-and-forget delete could not:

* a crash or a locked file between "row gone" and "file gone" leaves a visible pending row to retry,
  instead of a silent orphan;
* a rolled-back transaction removes the outbox row with it, so the file survives;
* every deletion has a ledger entry (done / still failing / abandoned) with attempts and last error.

status is a plain string (not a SQLAlchemy Enum) on purpose: Enum columns store member NAMES, which has
already bitten this codebase once.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_ABANDONED = "abandoned"


class MediaDeletion(Base, TimestampMixin):
    __tablename__ = "media_deletions"

    id: Mapped[int] = mapped_column(primary_key=True)
    secure_object_ref: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(60), nullable=False, default="retention")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=STATUS_PENDING, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
