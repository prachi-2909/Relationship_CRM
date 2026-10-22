"""Daily CSP birthday wishes - a relationship touchpoint.

Finds every ACTIVE CSP whose birthday is today and who has an email, and sends a short, warm wish
from the SBI team. Idempotent per day via Csp.last_birthday_wish_on, so running it twice (or the
scheduled job plus a manual trigger) never double-mails anyone."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.csp import Csp, CspStatus
from . import email as email_svc

logger = logging.getLogger("rcrm.birthdays")
settings = get_settings()


def _first_name(full_name: str) -> str:
    return (full_name or "").strip().split()[0] if full_name else "there"


def _message(csp: Csp) -> str:
    """Plain-text birthday body. The Gmail template adds the "Hi {name}," greeting and the branded
    sign-off itself, so this is just the message in between."""
    return (
        "Wishing you a very Happy Birthday from all of us at the SBI team! "
        "Thank you for the wonderful work you do as a Customer Service Point. "
        "Have a joyful day."
    )


def todays_birthday_csps(db: Session, today: date | None = None) -> list[Csp]:
    """Active CSPs whose birthday (month+day) is today and who have an email. Handles Feb 29 by
    treating it as Feb 28 in non-leap years."""
    today = today or date.today()
    mmdd = (today.month, today.day)
    rows = db.scalars(
        select(Csp).where(Csp.status == CspStatus.ACTIVE).where(Csp.date_of_birth.is_not(None))
    ).all()
    out = []
    for c in rows:
        dob = c.date_of_birth
        bd = (dob.month, dob.day)
        if bd == (2, 29) and not _is_leap(today.year):
            bd = (2, 28)
        if bd == mmdd and c.email and "@" in c.email:
            out.append(c)
    return out


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def send_birthday_wishes(db: Session, today: date | None = None, dry_run: bool = False) -> dict:
    """Send a wish to each CSP with a birthday today that hasn't already been wished today.
    Returns a summary. dry_run lists who WOULD be wished without sending or recording anything."""
    today = today or date.today()
    recipients = [c for c in todays_birthday_csps(db, today) if c.last_birthday_wish_on != today]
    # dry_run (explicit preview) OR the global draft-only testing switch: show the full email that
    # WOULD be sent, but never send and never mark anyone as wished.
    if dry_run or settings.email_draft_only:
        return {
            "date": today.isoformat(),
            "mode": "draft" if settings.email_draft_only and not dry_run else "dry_run",
            "would_send": len(recipients),
            "drafts": [
                {"csp_id": c.csp_id, "name": c.name, "email": c.email, "rm_name": c.rm_name,
                 "subject": settings.csp_birthday_subject, "message": _message(c)}
                for c in recipients
            ],
        }
    if not email_svc.is_configured():
        return {"date": today.isoformat(), "sent": 0,
                "error": "Gmail sender not configured (set gmail_mcp_api_key)", "pending": len(recipients)}

    sent = failed = 0
    for c in recipients:
        result = email_svc.send_email(
            to=c.email, name=_first_name(c.name), message=_message(c),
            subject=settings.csp_birthday_subject,
        )
        if result.ok:
            c.last_birthday_wish_on = today
            sent += 1
        else:
            failed += 1
    db.commit()
    summary = {"date": today.isoformat(), "sent": sent, "failed": failed, "candidates": len(recipients)}
    logger.info("birthday wishes: %s", summary)
    return summary


def run_daily() -> dict:
    """Scheduler entry point: own DB session, never raises."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        return send_birthday_wishes(db)
    except Exception:
        db.rollback()
        logger.exception("birthday wishes job failed")
        return {"error": "failed"}
    finally:
        db.close()
