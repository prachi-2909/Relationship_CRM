"""Password hashing. bcrypt directly — no passlib shim."""

import bcrypt

_MAX_BYTES = 72  # bcrypt truncates beyond this; reject rather than silently accept.


def hash_password(plain: str) -> str:
    if len(plain.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("Password too long")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
