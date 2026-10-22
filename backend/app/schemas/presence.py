from pydantic import BaseModel


class PresenceStatusOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    is_logged_in: bool
    is_online: bool
    last_active_at: str | None
