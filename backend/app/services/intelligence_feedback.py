"""Outcome feedback on relationship-intelligence suggestions, and the quality numbers built from it.

What counts as evidence
-----------------------
Only EXPLICIT human actions: someone pressing "useful" / "not useful" / "relevant" / "not relevant", and
the decisions people already make on commitments (accept, dismiss, mark done, close as not fulfilled,
merge, keep separate). Nothing is inferred. A call happening, a brief being confirmed, a commitment being
extracted or auto-expired is NEVER counted as "the recommendation was right"; the DC confirm flow's
"approved_with_brief" is deliberately not an acceptance because nobody reviewed that commitment on its
own. Rates are only reported once there are MIN_SAMPLE decisions behind them - below that the honest
answer is "not enough data", not a percentage.

How the evidence is used
------------------------
1. A suggestion YOU marked not useful / not relevant is hidden from YOU for SUPPRESS_DAYS (and the count
   of hidden items is shown, never silently dropped).
2. Once a kind of suggestion has MIN_SAMPLE ratings, kinds that people find more useful are listed first
   and the rest later (smoothed, stable). Nothing is ever removed from other people's view.
Everything else - what suggestions exist - stays rule-based and unchanged.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.commitment import CommitmentEvent
from ..models.intelligence_feedback import (
    POSITIVE_VERDICTS,
    TARGET_FOLLOWUP,
    TARGET_TALKING_POINT,
    VERDICTS,
    IntelligenceFeedback,
)
from ..models.user import User
from . import audit

MIN_SAMPLE = 10
SUPPRESS_DAYS = 30
NEUTRAL_SCORE = 0.5
_WS = re.compile(r"\s+")


def item_key(kind: str, text: str) -> str:
    """A stable id for a suggestion: the same kind + wording always has the same key."""
    norm = _WS.sub(" ", (text or "").strip().lower())
    return hashlib.sha1(f"{kind}|{norm}".encode("utf-8")).hexdigest()[:16]


def make_item(item_type: str, kind: str, text: str) -> dict:
    return {"key": item_key(kind, text), "type": item_type, "kind": kind, "text": text}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- applying feedback


def kind_scores(db: Session) -> dict[tuple[str, str], float]:
    """Smoothed usefulness per (type, kind), only for kinds with at least MIN_SAMPLE ratings."""
    counts: dict[tuple[str, str], list[int]] = {}
    for target_type, kind, verdict in db.execute(
        select(IntelligenceFeedback.target_type, IntelligenceFeedback.kind, IntelligenceFeedback.verdict)
    ):
        c = counts.setdefault((target_type, kind), [0, 0])
        c[1] += 1
        if verdict in POSITIVE_VERDICTS:
            c[0] += 1
    return {k: (pos + 1) / (n + 2) for k, (pos, n) in counts.items() if n >= MIN_SAMPLE}


def apply_feedback(
    db: Session, user_id: int | None, subject_type: str, subject_id: int, items: list[dict],
    now: datetime | None = None,
) -> tuple[list[dict], int]:
    """Personalise a raw suggestion list. Returns (items, hidden_count). Each item gains `my_verdict`."""
    now = now or datetime.now(timezone.utc)
    mine: dict[tuple[str, str], IntelligenceFeedback] = {}
    if user_id is not None:
        for row in db.scalars(
            select(IntelligenceFeedback)
            .where(IntelligenceFeedback.user_id == user_id)
            .where(IntelligenceFeedback.subject_type == subject_type)
            .where(IntelligenceFeedback.subject_id == subject_id)
        ).all():
            mine[(row.target_type, row.target_key)] = row

    out: list[dict] = []
    hidden = 0
    for it in items:
        row = mine.get((it["type"], it["key"]))
        if (
            row is not None
            and row.verdict not in POSITIVE_VERDICTS
            and _aware(row.updated_at) >= now - timedelta(days=SUPPRESS_DAYS)
        ):
            hidden += 1
            continue
        out.append({**it, "my_verdict": row.verdict if row else None})

    scores = kind_scores(db)
    if scores:
        out.sort(key=lambda it: -scores.get((it["type"], it["kind"]), NEUTRAL_SCORE))   # stable
    return out, hidden


# --------------------------------------------------------------------------- recording feedback


def submit(
    db: Session, user: User, subject_type: str, subject_id: int, target_type: str, key: str,
    verdict: str, note: str | None, current_items: list[dict],
) -> IntelligenceFeedback:
    """Record (or change) one person's verdict on one suggestion. The suggestion's kind and text are
    taken from what the SERVER currently generates, never from the client, so a verdict cannot be
    forged for a suggestion that does not exist."""
    if target_type not in VERDICTS:
        raise ValueError("unknown feedback target")
    if verdict not in VERDICTS[target_type]:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS[target_type])}")
    item = next((i for i in current_items if i["type"] == target_type and i["key"] == key), None)
    if item is None:
        raise LookupError("that suggestion is no longer available")

    row = db.scalar(
        select(IntelligenceFeedback)
        .where(IntelligenceFeedback.user_id == user.id)
        .where(IntelligenceFeedback.subject_type == subject_type)
        .where(IntelligenceFeedback.subject_id == subject_id)
        .where(IntelligenceFeedback.target_type == target_type)
        .where(IntelligenceFeedback.target_key == key)
    )
    clean_note = (note or "").strip()[:300] or None
    if row is None:
        row = IntelligenceFeedback(
            user_id=user.id, subject_type=subject_type, subject_id=subject_id,
            target_type=target_type, target_key=key, kind=item["kind"], text=item["text"][:500],
            verdict=verdict, note=clean_note,
        )
        db.add(row)
    else:
        row.verdict, row.note = verdict, clean_note
        row.kind, row.text = item["kind"], item["text"][:500]
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    audit.record(
        db, action="intelligence.feedback", entity_type=subject_type, entity_id=subject_id,
        actor_id=user.id, after={"target_type": target_type, "kind": item["kind"], "verdict": verdict},
    )
    db.commit()
    return row


# --------------------------------------------------------------------------- measuring quality


def _rate(positive: int, total: int) -> dict:
    enough = total >= MIN_SAMPLE
    return {"n": total, "positive": positive, "rate": round(positive / total, 3) if enough and total else None,
            "enough_data": enough}


def quality_metrics(db: Session) -> dict:
    """Evidence-based quality numbers. Every figure is built from explicit human decisions only."""
    result: dict = {"min_sample": MIN_SAMPLE, "generated_at": datetime.now(timezone.utc).isoformat()}

    # 1) explicit ratings of suggestions, overall and per kind
    for label, target in (("talking_points", TARGET_TALKING_POINT), ("followups", TARGET_FOLLOWUP)):
        per_kind: dict[str, list[int]] = {}
        for kind, verdict in db.execute(
            select(IntelligenceFeedback.kind, IntelligenceFeedback.verdict).where(
                IntelligenceFeedback.target_type == target
            )
        ):
            c = per_kind.setdefault(kind, [0, 0])
            c[1] += 1
            if verdict in POSITIVE_VERDICTS:
                c[0] += 1
        overall_pos = sum(p for p, _ in per_kind.values())
        overall_n = sum(n for _, n in per_kind.values())
        result[label] = {
            "overall": _rate(overall_pos, overall_n),
            "by_kind": {k: _rate(p, n) for k, (p, n) in sorted(per_kind.items())},
        }

    # 2) decisions people make on commitments (system-generated events have no actor and are ignored)
    events = db.scalars(select(CommitmentEvent).where(CommitmentEvent.actor_id.is_not(None))).all()
    count = lambda action: sum(1 for e in events if e.action == action)  # noqa: E731
    accepted, dismissed = count("accepted"), count("dismissed")
    done, cancelled = count("done"), count("cancelled")
    not_fulfilled = sum(1 for e in events if e.action in ("done", "cancelled") and (e.detail or {}).get("outcome") == "not_fulfilled")
    merged, separate = count("merged"), count("kept_separate")
    result["proposals"] = {"accepted": accepted, "dismissed": dismissed, **_rate(accepted, accepted + dismissed)}
    result["fulfilment"] = {
        "done": done, "closed_without_doing": cancelled, "reported_not_fulfilled": not_fulfilled,
        **_rate(done, done + cancelled),
    }
    result["duplicate_flags"] = {
        "confirmed_duplicate": merged, "different_after_all": separate, **_rate(merged, merged + separate),
        "note": "the share of flags a human agreed with (precision of the duplicate detector)",
    }
    return result


# --------------------------------------------------------------------------- retention


def purge_old(db: Session, now: datetime | None = None) -> int:
    """Delete feedback rows whose verdict was last touched more than intelligence_feedback_retention_days
    ago. Audited as one entry per run (a count - never the suggestion text)."""
    from ..config import get_settings

    days = get_settings().intelligence_feedback_retention_days
    now = now or datetime.now(timezone.utc)
    stale = db.scalars(
        select(IntelligenceFeedback).where(IntelligenceFeedback.updated_at < now - timedelta(days=days))
    ).all()
    for row in stale:
        db.delete(row)
    if stale:
        db.flush()
        audit.record(
            db, action="intelligence.feedback_purged", entity_type="intelligence_feedback",
            after={"count": len(stale), "retention_days": days},
        )
    return len(stale)
