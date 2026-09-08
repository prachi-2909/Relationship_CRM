"""Request/response models for authentication."""

from pydantic import BaseModel, ConfigDict, EmailStr

from ..models.user import Role, UserStatus


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: Role
    status: UserStatus
