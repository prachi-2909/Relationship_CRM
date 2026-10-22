"""DC app presence: is the mobile app actually in the foreground right now.

The Android app pings /presence/heartbeat every ~20s while in the foreground
and /presence/background once when it leaves the foreground. "Online" also
requires a recent heartbeat (not just the foreground flag) so a killed app -
which never gets to send the background signal - still falls back to offline
within one missed-heartbeat window instead of showing "online" forever.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models.user import User

# Real interval is ~20s (HEARTBEAT_INTERVAL in the Android app) - 2x that plus
# slack for network latency/backgrounding jitter before we call it stale.
ONLINE_WINDOW_SECONDS = 45


def is_online(user: User) -> bool:
    if not user.is_app_foreground or user.last_active_at is None:
        return False
    last_active = user.last_active_at
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_active < timedelta(seconds=ONLINE_WINDOW_SECONDS)


def record_heartbeat(user: User) -> None:
    user.is_app_foreground = True
    user.last_active_at = datetime.now(timezone.utc)


def record_background(user: User) -> None:
    user.is_app_foreground = False
