"""In-memory login throttle: locks an account/IP out after too many failed attempts.

Deliberately process-local and dependency-free - the app runs as a single Uvicorn process
against SQLite, so a shared store (Redis) would be over-engineering here. If the deployment ever
scales to multiple workers this must move to a shared backend; until then this is the first line
against password brute-forcing and credential stuffing, and it is paired with a constant-time
dummy verify in the login route so a wrong email and a wrong password cost the same.
"""

from __future__ import annotations

import threading
import time

_WINDOW_SECONDS = 15 * 60  # attempts older than this no longer count
_MAX_FAILURES = 3  # wrong-password attempts within the window before the account/IP is locked
_LOCKOUT_SECONDS = 15 * 60  # how long the lockout lasts once tripped

_lock = threading.Lock()
# key -> (failure timestamps within window, locked_until epoch)
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def _key(email: str, ip: str) -> str:
    return f"{email.strip().lower()}|{ip}"


def retry_after_seconds(email: str, ip: str, now: float | None = None) -> int:
    """0 when a login may proceed, else the seconds remaining on the lockout."""
    now = time.time() if now is None else now
    with _lock:
        until = _locked_until.get(_key(email, ip))
        if until is not None and until > now:
            return int(until - now) + 1
        return 0


def record_failure(email: str, ip: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    key = _key(email, ip)
    with _lock:
        recent = [t for t in _failures.get(key, []) if now - t < _WINDOW_SECONDS]
        recent.append(now)
        _failures[key] = recent
        if len(recent) >= _MAX_FAILURES:
            _locked_until[key] = now + _LOCKOUT_SECONDS
            _failures[key] = []


def record_success(email: str, ip: str) -> None:
    key = _key(email, ip)
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def reset() -> None:
    """Test hook: clears all throttle state."""
    with _lock:
        _failures.clear()
        _locked_until.clear()
