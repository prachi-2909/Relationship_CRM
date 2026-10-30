"""Relationship score for a CSP (kiosk operator), the way an RM needs to read it.

The same transparent method as the official's score (services/scoring.py): a weighted average of signals, each
0-100; a signal that cannot be computed yet returns None and its weight is shared out over the rest; the weight
version is recorded with every result; the bands are the same. Everything here is plain arithmetic on figures the
CRM or TARA holds, with a reason in words for every signal. No AI is involved, so the same inputs always give the
same score.

Three numbers come out, because an RM acts differently on each:
- relationship: how warm the working relationship is (contact, follow-through, does the CSP pick up).
- business: how the CSP is doing against its targets, from TARA (performance against target, trend).
- overall: all five signals together.
A CSP with a warm relationship and weak business needs help; one with both cold and weak needs a call first.

The two TARA signals are left out of the average (and `tara_included` is false) whenever TARA's figures are not
passed in, so the score is never built on a guess.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.call_intelligence import CallSession, CallSessionStatus
from ..models.commitment import Commitment, CommitmentStatus
from ..models.csp import Csp
from ..models.interaction import Direction
from . import tara_panel
from .scoring import band

WEIGHTS_VERSION = "csp-v1-2026-10"
WEIGHTS: dict[str, float] = {
    "recency": 20.0,            # relationship
    "answered": 10.0,           # relationship
    "followthrough": 20.0,      # relationship
    "tara_performance": 30.0,   # business
    "tara_trend": 20.0,         # business
}
GROUPS = {
    "relationship": ("recency", "answered", "followthrough"),
    "business": ("tara_performance", "tara_trend"),
}
RECENCY_ZERO_AFTER_DAYS = 30      # a CSP works to a monthly slab, so a month without contact scores 0
ANSWERED_WINDOW_DAYS = 60
COMMITMENT_WINDOW_DAYS = 90
LATE_COUNTS_AS = 0.5              # a commitment done after its due date counts for half


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _recency(db: Session, csp: Csp, now: datetime) -> tuple[float | None, str]:
    last = db.scalar(
        select(CallSession.started_at)
        .where(CallSession.csp_id == csp.id, CallSession.processing_status != CallSessionStatus.CANCELLED)
        .order_by(CallSession.started_at.desc())
        .limit(1)
    )
    if last is None:
        return 0.0, "No call with this CSP is on record."
    days = max(0, (now - _aware(last)).days)
    value = max(0.0, 100.0 - days / RECENCY_ZERO_AFTER_DAYS * 100.0)
    when = "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"
    return round(value, 1), f"Last call was {when}."


def _answered(db: Session, csp: Csp, now: datetime) -> tuple[float | None, str]:
    since = now - timedelta(days=ANSWERED_WINDOW_DAYS)
    rows = db.execute(
        select(CallSession.processing_status, CallSession.ended_at)
        .where(CallSession.csp_id == csp.id, CallSession.direction == Direction.OUTBOUND, CallSession.started_at >= since)
    ).all()
    # An attempt counts only once it was reported back: a call that connected, or one that rang out unanswered.
    connected = sum(1 for status, _ in rows if status != CallSessionStatus.CANCELLED)
    unanswered = sum(1 for status, ended in rows if status == CallSessionStatus.CANCELLED and ended is not None)
    attempts = connected + unanswered
    if attempts == 0:
        return None, ""
    value = connected / attempts * 100.0
    return round(value, 1), f"Picked up {connected} of {attempts} calls in the last {ANSWERED_WINDOW_DAYS} days."


def _followthrough(db: Session, csp: Csp, now: datetime) -> tuple[float | None, str]:
    today = now.date()
    since = now - timedelta(days=COMMITMENT_WINDOW_DAYS)
    rows = db.scalars(
        select(Commitment).where(
            Commitment.csp_id == csp.id,
            Commitment.merged_into_id.is_(None),
            Commitment.status.in_([CommitmentStatus.OPEN, CommitmentStatus.DONE]),
            Commitment.created_at >= since,
        )
    ).all()
    on_time = late = overdue = 0
    for c in rows:
        if c.status == CommitmentStatus.DONE:
            done_day: date | None = _aware(c.done_at).date() if c.done_at else None
            if c.due_date is None or done_day is None or done_day <= c.due_date:
                on_time += 1
            else:
                late += 1
        elif c.due_date is not None and c.due_date < today:
            overdue += 1
        # an open commitment that is not due yet is neither kept nor broken: it is left out
    due = on_time + late + overdue
    if due == 0:
        return None, ""
    value = (on_time + LATE_COUNTS_AS * late) / due * 100.0
    parts = [f"{on_time} kept on time"]
    if late:
        parts.append(f"{late} done late")
    if overdue:
        parts.append(f"{overdue} overdue")
    return round(value, 1), "Commitments: " + ", ".join(parts) + "."


def _tara_performance(tara: dict | None, today: date) -> tuple[float | None, str]:
    """The four core schemes against TARA's goals, allowing for how much of the month has gone."""
    return tara_panel.performance_signal(tara, today)


def _tara_trend(tara: dict | None) -> tuple[float | None, str]:
    """Earnings and transactions against the CSP's own usual, from TARA's growth figures."""
    return tara_panel.trend_signal(tara)


def _weighted(values: dict[str, float | None], names: tuple[str, ...]) -> float | None:
    pairs = [(values[n], WEIGHTS[n]) for n in names if values.get(n) is not None]
    total = sum(w for _, w in pairs)
    if total == 0:
        return None
    return round(sum(v * w for v, w in pairs) / total, 1)


def score_csp(db: Session, csp: Csp, *, now: datetime | None = None, tara: dict | None = None) -> dict:
    """`tara` is TARA's `csp_performance` data for this CSP (None when TARA is off or gave nothing)."""
    now = now or datetime.now(timezone.utc)
    computed = {
        "recency": _recency(db, csp, now),
        "answered": _answered(db, csp, now),
        "followthrough": _followthrough(db, csp, now),
        "tara_performance": _tara_performance(tara, now.date()),
        "tara_trend": _tara_trend(tara),
    }
    values = {name: computed[name][0] for name in WEIGHTS}
    overall = _weighted(values, tuple(WEIGHTS))
    relationship = _weighted(values, GROUPS["relationship"])
    business = _weighted(values, GROUPS["business"])

    # Words for every signal that was computed, the weakest first, so the RM reads what to fix before what is fine.
    notes = sorted(
        ((values[n], computed[n][1]) for n in WEIGHTS if values[n] is not None and computed[n][1]),
        key=lambda pair: pair[0],
    )
    return {
        "version": WEIGHTS_VERSION,
        "overall": None if overall is None else round(overall),
        "relationship": None if relationship is None else round(relationship),
        "business": None if business is None else round(business),
        "band": band(round(overall))[0] if overall is not None else None,
        "tara_included": business is not None,
        "components": {
            name: {"value": values[name], "weight": WEIGHTS[name], "note": computed[name][1] or None}
            for name in WEIGHTS
        },
        "reasons": [text for _, text in notes],
    }
