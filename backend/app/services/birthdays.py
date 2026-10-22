"""Daily CSP birthday wishes - a relationship touchpoint.

Finds every ACTIVE CSP whose birthday is today and who has an email, and sends a short, warm,
PERSONALISED, BILINGUAL wish (Hindi + English in one mail, so every Kiosk Operator can read it)
from the Eko relationship team. Idempotent per day via Csp.last_birthday_wish_on, so running it
twice (or the scheduled job plus a manual trigger) never double-mails anyone."""

from __future__ import annotations

import json
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.call_intelligence import CallSession
from ..models.csp import Csp, CspStatus
from . import email as email_svc

logger = logging.getLogger("rcrm.birthdays")
settings = get_settings()

_DIVIDER = "\n\n───────────────\n\n"

# The five products a CSP sells; used to pull a concrete, quantified achievement to praise.
_PRODUCT = re.compile(r"PM[\- ]?JJBY|PM[\- ]?SBY|PMJDY|APY|SSS|SSY|Sukanya", re.I)
# Only praise genuinely positive, completed work - never a birthday "reminder" about what's pending.
_POSITIVE = re.compile(r"\b(done|completed|achiev)", re.I)
_NEGATIVE = re.compile(r"pending|remaining|not yet|issue|expiry|fix|missing|failed|concern|short", re.I)


# Leading titles/honorifics that aren't a given name - skipped so "Md Jamshed" greets "Jamshed",
# "Dr Mohd Imran" greets "Imran", etc.
_HONORIFICS = {
    "md", "mohd", "mohammad", "mohammed", "mohammd", "muhammad", "mohd.",
    "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "shri", "sri", "smt", "smt.",
    "dr", "dr.", "km", "km.", "kum", "kumari", "master", "sh", "sh.",
}


def _first_name(full_name: str) -> str:
    """First given name for the greeting, skipping leading honorifics (Md/Mohd/Dr/Smt...). Falls back
    to the first token if every token is an honorific, or 'there' if there's no name at all."""
    tokens = (full_name or "").strip().split()
    if not tokens:
        return "there"
    for tok in tokens:
        if tok.lower().strip(".") not in {h.strip(".") for h in _HONORIFICS}:
            return tok
    return tokens[0]


def _achievement(db: Session, csp: Csp) -> str | None:
    """A concrete, positive, quantified product achievement from this CSP's most recent call brief
    (e.g. "26 PMSBY"), or None. Only real, completed figures - nothing invented, nothing pending."""
    calls = db.scalars(
        select(CallSession)
        .where(CallSession.csp_id == csp.id)
        .order_by(CallSession.started_at.desc())
    ).all()
    for call in calls:
        if not call.analysis:
            continue
        for raw in call.analysis.analysis_json.get("highlights") or []:
            h = (raw or "").replace("‑", "-").replace("‐", "-")
            if _NEGATIVE.search(h) or not _POSITIVE.search(h):
                continue
            prod = _PRODUCT.search(h)
            num = re.search(r"\d+", h)
            if prod and num:
                return f"{num.group(0)} {prod.group(0).upper().replace(' ', '').replace('-', '')}"
    return None


def _facts(db: Session, csp: Csp) -> dict:
    return {
        "name": csp.name or "",
        "first": _first_name(csp.name),
        "tier": csp.category,          # e.g. "Gold CSP"
        "branch": csp.branch_name,
        "state": csp.state,
        "rm": csp.rm_name,
        "achievement": _achievement(db, csp),
    }


def _appreciation(facts: dict) -> tuple[str, str]:
    """(hindi, english) appreciation line, tailored to what we actually know about the CSP."""
    tier, branch, ach = facts["tier"], facts["branch"], facts["achievement"]
    at_hi = f"{branch} में " if branch else ""
    at_en = f" at {branch}" if branch else ""
    if tier and ach:
        return (
            f"{at_hi}आप हमारे {tier} हैं — इस बार आपके {ach} का काम शानदार रहा। "
            "ग्राहकों की सेवा में आपकी मेहनत बेहद सराहनीय है।",
            f"As our {tier}{at_en}, your {ach} this cycle really stood out — "
            "wonderful work serving your customers.",
        )
    if tier:
        return (
            f"{at_hi}आप हमारे {tier} हैं, और आपकी मेहनत हमेशा सराहनीय रही है।",
            f"As our {tier}{at_en}, your dedication always stands out.",
        )
    if ach:
        return (
            f"इस बार आपके {ach} का काम शानदार रहा — आपकी मेहनत सराहनीय है।",
            f"Your {ach} this cycle really stood out — wonderful work.",
        )
    return (
        "Customer Service Point के रूप में आपका काम बेहद सराहनीय है।",
        "Thank you for the wonderful work you do as a Customer Service Point.",
    )


def _default_subject(first: str) -> str:
    return f"जन्मदिन मुबारक हो, {first} जी! / Happy Birthday, {first}! 🎂"


def _deterministic(facts: dict) -> dict:
    """Safe bilingual draft built straight from facts - used as-is when no LLM is configured, and as
    the fallback when one is. Never invents anything. NO greeting or sign-off here: the Gmail template
    adds "Hi {name}," at the top and the Eko sign-off at the bottom, so adding our own would double up."""
    first = facts["first"]
    hi_appr, en_appr = _appreciation(facts)
    hindi = (
        "जन्मदिन की आपको हमारी पूरी Eko टीम की ओर से हार्दिक शुभकामनाएँ! 🎉\n\n"
        f"{hi_appr}\n\n"
        "आप जैसे समर्पित CSP पर हमें गर्व है — इसी जोश और मेहनत के साथ आगे बढ़ते रहिए, "
        "आपकी हर कोशिश ग्राहकों की ज़िंदगी में फ़र्क लाती है। आने वाला साल आपके लिए ढेरों कामयाबियाँ लेकर आए! 🎉"
    )
    english = (
        "Warm birthday wishes from your entire Eko team! 🎉\n\n"
        f"{en_appr}\n\n"
        "We're proud to have a CSP as dedicated as you — keep moving forward with the same energy, "
        "because every effort you make changes lives in your community. Here's to a year full of success ahead! 🎉"
    )
    return {
        "subject": _default_subject(first),
        "message": hindi + _DIVIDER + english,
        "generated_by": "template",
    }


def _llm_draft(facts: dict) -> dict | None:
    """Ask the configured LLM for a warmer bilingual draft from the SAME facts. Returns None (so the
    caller falls back to the template) when no endpoint is set or anything looks wrong."""
    from . import llm

    system = (
        "You write a warm, short, BILINGUAL birthday message for a State Bank of India Customer "
        "Service Point (CSP / Bank Mitra), sent by the Eko relationship team. Write the Hindi version "
        "first (in Devanagari), then the English version. Celebratory, warm and personal, and also "
        "MOTIVATING - appreciate their work and encourage them to keep it up with energy; do NOT tell "
        "them to 'forget work/targets'. Never scold or list pending targets. Use ONLY the facts in the "
        "input - never invent a number, product, branch or achievement; omit anything not given. "
        "IMPORTANT: do NOT add any greeting (no 'Hi'/'नमस्ते'/name line) and NO sign-off/'regards' - the "
        "email template already adds 'Hi {name},' at the top and the Eko sign-off at the bottom, so "
        "start directly with the birthday wish. Reply with ONLY a JSON object: "
        '{"subject": str, "hindi": str, "english": str}.'
    )
    user = json.dumps(
        {k: facts[k] for k in ("name", "first", "tier", "branch", "achievement", "rm")},
        ensure_ascii=False,
    )
    out = llm.chat(system, user, temperature=0.6)
    if not out:
        return None
    try:
        data = json.loads(llm._json_blob(out))
    except Exception:
        return None
    hi, en = (data.get("hindi") or "").strip(), (data.get("english") or "").strip()
    if not hi or not en:
        return None
    return {
        "subject": (data.get("subject") or "").strip() or _default_subject(facts["first"]),
        "message": hi + _DIVIDER + en,
        "generated_by": settings.llm_model,
    }


def personalize(db: Session, csp: Csp) -> dict:
    """One CSP's bilingual, personalised birthday draft: {subject, message, generated_by}. Uses the
    LLM when configured, else a safe deterministic template - both from the same real facts."""
    facts = _facts(db, csp)
    return _llm_draft(facts) or _deterministic(facts)


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


def _days_until(dob: date, today: date) -> int:
    """Days from today to the next occurrence of this birthday (0 = today)."""
    try:
        nxt = dob.replace(year=today.year)
    except ValueError:  # Feb 29 in a non-leap year
        nxt = date(today.year, 2, 28)
    if nxt < today:
        try:
            nxt = dob.replace(year=today.year + 1)
        except ValueError:
            nxt = date(today.year + 1, 2, 28)
    return (nxt - today).days


def upcoming_birthday_csps(
    db: Session, days: int = 7, today: date | None = None
) -> list[tuple[Csp, int]]:
    """Active CSPs with an email whose birthday falls in the next `days` days (1..days, excluding
    today), each with how many days away it is - for previewing the wishes that are coming up."""
    today = today or date.today()
    out: list[tuple[Csp, int]] = []
    for c in db.scalars(
        select(Csp).where(Csp.status == CspStatus.ACTIVE).where(Csp.date_of_birth.is_not(None))
    ).all():
        if not (c.email and "@" in c.email):
            continue
        d = _days_until(c.date_of_birth, today)
        if 1 <= d <= days:
            out.append((c, d))
    out.sort(key=lambda x: x[1])
    return out


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
                 **personalize(db, c)}
                for c in recipients
            ],
        }
    if not email_svc.is_configured():
        return {"date": today.isoformat(), "sent": 0,
                "error": "Gmail sender not configured (set gmail_mcp_api_key)", "pending": len(recipients)}

    sent = failed = 0
    for c in recipients:
        draft = personalize(db, c)
        result = email_svc.send_email(
            to=c.email, name=_first_name(c.name), message=draft["message"],
            subject=draft["subject"],
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
