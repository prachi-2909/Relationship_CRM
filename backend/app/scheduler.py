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
from .services import (
    agent,
    audit,
    backup,
    call_intelligence,
    moments,
    outcomes,
    retention,
    scoring,
    strategic_insight,
)
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
        n_expired = agent.expire_stale_recommendations(db)
        n_agent_recs = 0
        if settings.enable_agent:
            n_agent_recs = agent.run_nightly(db).recommendations_created
        n_insights = strategic_insight.recompute_all(db)
        outcomes.create_missing_outcomes(db)
        n_resolved = outcomes.reconcile_pending(db)
        n_audio_purged = call_intelligence.purge_stale_call_audio(db)
        db.commit()
        # RM audio (60d), failed-delete retries, orphan files, commitment lifecycle - each step
        # commits or rolls back on its own so one failure cannot block the rest.
        retention_summary = retention.run_nightly(db)
        backup_path = backup.create_backup() if settings.enable_backups else None
        logger.info(
            "nightly: rescored %s relationships, escalated %s tasks, detected %s moments, "
            "agent created %s recommendation(s) (%s expired), %s strategic insight(s), "
            "%s outcome(s) resolved, %s unlogged call(s)' audio expired, retention %s, backup %s",
            n_scores,
            n_overdue,
            n_moments,
            n_agent_recs,
            n_expired,
            n_insights,
            n_resolved,
            n_audio_purged,
            retention_summary,
            backup_path or "skipped",
        )
    except Exception:  # pragma: no cover - defensive
        db.rollback()
        logger.exception("nightly job failed")
    finally:
        db.close()


def _csp_sync_job() -> None:
    """Daily 8 PM IST: re-sync CSP name/number/RM from the live calling sheet."""
    from .services import csp_sync

    csp_sync.run_sync()


def _csp_birthday_job() -> None:
    """Daily morning: email a birthday wish to every CSP whose birthday is today."""
    from .services import birthdays

    birthdays.run_daily()


def _recover_transcriptions_once() -> None:
    """One-shot at startup: finish any transcription stranded at TRANSCRIBING by a prior restart.
    Runs in its own thread so loading the whisper model never blocks app boot."""
    try:
        n = call_intelligence.recover_stuck_transcriptions()
        if n:
            logger.info("recovered %s stuck transcription(s) after restart", n)
    except Exception:  # pragma: no cover - defensive
        logger.exception("transcription recovery sweep failed")


def start_scheduler() -> None:
    global _scheduler
    if not settings.enable_scheduler or _scheduler is not None:
        return
    import threading

    threading.Thread(target=_recover_transcriptions_once, daemon=True).start()

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _nightly_job, CronTrigger(hour=3, minute=0), id="nightly", replace_existing=True
    )
    if settings.csp_sync_enabled:
        _scheduler.add_job(
            _csp_sync_job,
            CronTrigger(hour=settings.csp_sync_hour, minute=0, timezone=settings.csp_sync_timezone),
            id="csp_sync",
            replace_existing=True,
        )
    if settings.csp_birthday_wishes_enabled:
        _scheduler.add_job(
            _csp_birthday_job,
            CronTrigger(hour=settings.csp_birthday_hour, minute=0, timezone=settings.csp_sync_timezone),
            id="csp_birthday",
            replace_existing=True,
        )
    _scheduler.start()
    logger.info(
        "scheduler started (nightly 03:00 UTC%s)",
        f", CSP sync {settings.csp_sync_hour:02d}:00 {settings.csp_sync_timezone}"
        if settings.csp_sync_enabled else "",
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
