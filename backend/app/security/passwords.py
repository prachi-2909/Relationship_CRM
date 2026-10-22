"""Password hashing. bcrypt directly — no passlib shim."""

import bcrypt

_MAX_BYTES = 72  # bcrypt truncates beyond this; reject rather than silently accept.

# A real bcrypt hash of a throwaway string. Verifying a submitted password against THIS when the
# email doesn't exist makes a wrong email cost the same as a wrong password, so an attacker can't
# tell registered emails apart by response time (user enumeration).
_DUMMY_HASH = "$2b$12$vFBB7vzO5RRYBUQ6ZF9PtOt1tMbCvbqr97ctA1Vku4tEt7u8TAVwa"


def verify_dummy(plain: str) -> None:
    """Constant-time guard for the unknown-user branch of login. Always returns None."""
    verify_password(plain, _DUMMY_HASH)


def hash_password(plain: str) -> str:
    if len(plain.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("Password too long")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
