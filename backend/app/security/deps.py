"""Auth dependencies: resolve the current user, and gate routes by role."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models.user import Role, User, UserStatus
from .sessions import resolve_session

settings = get_settings()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    session = resolve_session(db, token)
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalid or expired")

    user = db.get(User, session.user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account inactive")
    return user


def require_roles(*roles: Role):
    """Dependency factory: allow only the listed roles."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dependency
