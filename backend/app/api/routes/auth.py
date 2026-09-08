"""Login, logout, and current-user endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.user import User, UserStatus
from ...schemas.auth import LoginRequest, UserOut
from ...security.deps import get_current_user
from ...security.passwords import verify_password
from ...security.sessions import create_session, revoke_session
from ...services import audit

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user.status is not UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    token = create_session(db, user.id)
    audit.record(
        db, action="auth.login", entity_type="user", entity_id=user.id, actor_id=user.id
    )
    db.commit()
    _set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        revoke_session(db, token)
    audit.record(
        db, action="auth.logout", entity_type="user", entity_id=user.id, actor_id=user.id
    )
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
