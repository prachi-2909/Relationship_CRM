"""Login, logout, and current-user endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.user import User, UserStatus
from ...schemas.auth import LoginRequest, LoginResponse, UserOut
from ...security import login_throttle
from ...security.deps import get_current_user
from ...security.passwords import verify_dummy, verify_password
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


def _client_ip(request: Request) -> str:
    # X-Forwarded-For's first hop when behind nginx, else the socket peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower()
    ip = _client_ip(request)

    retry_after = login_throttle.retry_after_seconds(email, ip)
    if retry_after:
        audit.record(
            db, action="auth.login_throttled", entity_type="user", entity_id=None,
            actor_id=None, after={"email": email, "ip": ip},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_dummy(payload.password)  # equalise timing so a wrong email isn't distinguishable
        password_ok = False
    else:
        password_ok = verify_password(payload.password, user.password_hash)

    if user is None or not password_ok:
        login_throttle.record_failure(email, ip)
        audit.record(
            db, action="auth.login_failed", entity_type="user",
            entity_id=user.id if user else None, actor_id=user.id if user else None,
            after={"email": email, "ip": ip},
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if user.status is not UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    login_throttle.record_success(email, ip)
    token = create_session(db, user.id)
    audit.record(
        db, action="auth.login", entity_type="user", entity_id=user.id, actor_id=user.id
    )
    db.commit()
    _set_session_cookie(response, token)
    return LoginResponse(**UserOut.model_validate(user).model_dump(), token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Revoke whichever token this request authenticated with - the cookie (web) OR the
    # Authorization: Bearer token (the native app). Before this, a mobile logout left the bearer
    # token valid for its full lifetime.
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip() or None
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
