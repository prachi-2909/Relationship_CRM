"""Person-to-person connections between officials.

An edge in the stakeholder graph: who reports to whom, who works with whom,
who introduced us to whom. Edges are asserted manually by an RM or *suggested*
by the system (e.g. two officials co-mentioned in one interaction) and then
confirmed or dismissed by a human — the same detect-then-confirm loop used for
provenance and engagement moments.
"""

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ConnectionType(str, enum.Enum):
    REPORTS_TO = "reports_to"        # directed: from reports to -> to
    WORKS_WITH = "works_with"        # undirected
    INTRODUCED_BY = "introduced_by"  # directed: from was introduced by -> to


class ConnectionStatus(str, enum.Enum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


# For these types the (from, to) order carries meaning. WORKS_WITH is stored
# with from_official_id < to_official_id so A-B and B-A collapse to one row.
DIRECTED_TYPES = frozenset({ConnectionType.REPORTS_TO, ConnectionType.INTRODUCED_BY})

_type = SAEnum(ConnectionType, native_enum=False, length=20, name="connection_type")
_status = SAEnum(
    ConnectionStatus, native_enum=False, length=16, name="connection_status"
)


class Connection(Base, TimestampMixin):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint(
            "from_official_id", "to_official_id", "type", name="uq_connection_pair_type"
        ),
        CheckConstraint(
            "from_official_id <> to_official_id", name="ck_connection_not_self"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[ConnectionType] = mapped_column(_type, nullable=False, index=True)
    status: Mapped[ConnectionStatus] = mapped_column(
        _status, nullable=False, default=ConnectionStatus.SUGGESTED, index=True
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_interaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    from_official = relationship(
        "Official", foreign_keys=[from_official_id], lazy="joined"
    )
    to_official = relationship("Official", foreign_keys=[to_official_id], lazy="joined")
