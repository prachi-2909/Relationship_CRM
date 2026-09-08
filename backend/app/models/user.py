"""User accounts and their roles."""

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Role(str, enum.Enum):
    ADMIN = "admin"
    RELATIONSHIP_MANAGER = "relationship_manager"
    APPROVER_VIEWER = "approver_viewer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


# native_enum=False -> stored as VARCHAR + CHECK, portable across SQLite/Postgres.
_role = SAEnum(Role, native_enum=False, length=32, name="user_role")
_status = SAEnum(UserStatus, native_enum=False, length=16, name="user_status")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        _role, nullable=False, default=Role.RELATIONSHIP_MANAGER
    )
    status: Mapped[UserStatus] = mapped_column(
        _status, nullable=False, default=UserStatus.ACTIVE
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<User {self.id} {self.email} {self.role.value}>"
