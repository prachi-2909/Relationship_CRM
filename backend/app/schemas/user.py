"""Request models for user administration. Responses reuse ``UserOut``."""

from pydantic import BaseModel, EmailStr, Field

from ..models.user import Role, UserStatus
from .auth import UserOut

__all__ = ["UserCreate", "UserUpdate", "UserOut"]


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: Role = Role.RELATIONSHIP_MANAGER


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    status: UserStatus | None = None
