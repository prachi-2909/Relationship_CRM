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


class LoginResponse(UserOut):
    """UserOut plus the raw session token, for a mobile client - it can't read an
    httpOnly cookie, so it stores this and sends it back as `Authorization: Bearer`.
    The web client keeps using the cookie and simply ignores this field."""

    token: str
