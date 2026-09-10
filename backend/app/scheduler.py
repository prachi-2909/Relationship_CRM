"""Background jobs: nightly score recompute and the overdue-task sweep.

Enabled by ``settings.enable_scheduler`` (off in tests). The sweep is also
exposed as an endpoint so it can be run on demand.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models.relationship import Relationship
from .models.task import Task, TaskStatus
from .services import audit, moments, scoring
from .services.importance import recompute as recompute_importance

logger = logging.getLogger("rcrm.scheduler")
settings = get_settings()

_scheduler = None


def recompute_all_scores(db: Session) -> int:
    rels = db.scalars(select(Relationship)).all()
    for rel in rels:
        recompute_importance(db, rel)
        scoring.recompute_and_store(db, rel, reason="nightly")
    db.flush()
    return len(rels)


def sweep_overdue_tasks(db: Session) -> int:
    """Stamp newly-overdue open tasks and log an escalation. Returns count."""
    now = datetime.now(timezone.utc)
    overdue = db.scalars(
        select(Task)
        .where(Task.status == TaskStatus.OPEN)
        .where(Task.due_at.is_not(None))
        .where(Task.due_at < now)
        .where(Task.escalated_at.is_(None))
    ).all()
    for task in overdue:
        task.escalated_at = now
        audit.record(
            db,
            action="task.overdue_escalated",
            entity_type="task",
            entity_id=task.id,
            after={"title": task.title, "due_at": task.due_at.isoformat()},
        )
    db.flush()
    return len(overdue)


def _nightly_job() -> None:
    db = SessionLocal()
    try:
        n_scores = recompute_all_scores(db)
        n_overdue = sweep_overdue_tasks(db)
        n_moments = moments.detect_all(db)
        db.commit()
        logger.info(
            "nightly: rescored %s relationships, escalated %s tasks, detected %s moments",
            n_scores,
            n_overdue,
            n_moments,
        )
    except Exception:  # pragma: no cover - defensive
        db.rollback()
        logger.exception("nightly job failed")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if not settings.enable_scheduler or _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _nightly_job, CronTrigger(hour=3, minute=0), id="nightly", replace_existing=True
    )
    _scheduler.start()
    logger.info("scheduler started (nightly 03:00 UTC)")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
