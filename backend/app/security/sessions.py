"""Create, resolve, and revoke server-side sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.session import UserSession

settings = get_settings()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat stored times as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=_hash_token(token),
            created_at=now,
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
        )
    )
    db.flush()
    return token


def resolve_session(db: Session, token: str) -> UserSession | None:
    row = db.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    )
    if row is None or row.revoked_at is not None:
        return None
    if _as_aware(row.expires_at) <= datetime.now(timezone.utc):
        return None
    return row


def revoke_session(db: Session, token: str) -> None:
    row = db.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.flush()
