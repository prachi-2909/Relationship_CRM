"""Retention enforcement for call media and derived records.

Three separate streams, three separate rules (full table in docs/data-retention.md):

* DC <-> SBI official calls: audio is deleted when the interaction is logged, and unlogged audio after
  unconfirmed_call_audio_retention_days. That logic lives in services/call_intelligence.py and is NOT
  changed here.
* RM <-> CSP calls: the AUDIO is deleted rm_recording_retention_days (60) after it was stored. Only the
  audio. The transcript and the AI brief are explicitly left alone - they are not part of this purge.
* Housekeeping that makes deletion trustworthy: failed deletions are retried (outbox), files nothing
  references are removed (orphan sweep), and every destructive action leaves an audit entry.

Every function takes the caller's session and only flushes; run_nightly commits step by step so one
failing step cannot block, or roll back, the others.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.call_intelligence import (
    CallRecording,
    CallSession,
    CallSessionStatus,
    CallTranscript,
    CallVoiceNote,
)
from ..models.media_deletion import STATUS_DONE, STATUS_PENDING, MediaDeletion
from . import audit
from . import commitments as commitments_svc
from . import media_storage
from .call_intelligence import rm_retains_recording

logger = logging.getLogger("rcrm.retention")
settings = get_settings()

# How long finished outbox rows are kept as a ledger before housekeeping drops them. (The audit log
# keeps the durable record of anything that failed or was retried.)
LEDGER_KEEP_DAYS = 90


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- RM audio (audio ONLY)


def purge_expired_rm_audio(db: Session, now: datetime | None = None, dry_run: bool = False) -> int:
    """Delete the AUDIO of RM-CSP calls older than rm_recording_retention_days. Returns the number of
    calls whose audio was (or, with dry_run, would be) removed.

    Deliberately touches nothing but CallVoiceNote / CallRecording rows and their files: the
    transcript and the AI brief stay, so a retained transcript still backs the call's history,
    commitments and relationship memory. DC calls are never handled here."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.rm_recording_retention_days)
    call_ids = set(
        db.scalars(select(CallVoiceNote.call_session_id).where(CallVoiceNote.created_at < cutoff))
    ) | set(db.scalars(select(CallRecording.call_session_id).where(CallRecording.created_at < cutoff)))

    purged = 0
    for call_id in sorted(call_ids):
        call = db.get(CallSession, call_id)
        if call is None or not rm_retains_recording(call):
            continue  # not an RM call: the DC rules (services/call_intelligence.py) own it
        existing = [
            r
            for r in (
                db.scalar(select(CallVoiceNote).where(CallVoiceNote.call_session_id == call.id)),
                db.scalar(select(CallRecording).where(CallRecording.call_session_id == call.id)),
            )
            if r is not None
        ]
        expired = [r for r in existing if _aware(r.created_at) < cutoff]
        if not expired:
            continue
        purged += 1
        if dry_run:
            continue

        had_transcript = (
            db.scalar(select(CallTranscript.id).where(CallTranscript.call_session_id == call.id)) is not None
        )
        age_days = max((now - _aware(r.created_at)).days for r in expired)
        for r in expired:
            if media_storage.is_local_ref(r.secure_object_ref):
                media_storage.delete_after_commit(db, r.secure_object_ref, reason="rm_retention_expired")
            db.delete(r)
        if len(expired) == len(existing):
            call.recording_status = CallSessionStatus.PURGED
        db.flush()
        audit.record(
            db, action="call.audio_purged_retention_expired", entity_type="call_session", entity_id=call.id,
            after={
                "stream": "rm_csp", "scope": "audio_only", "files": len(expired), "age_days": age_days,
                "retention_days": settings.rm_recording_retention_days,
                "had_transcript": had_transcript, "transcript_retained": True,
            },
        )
    return purged


# --------------------------------------------------------------------------- failed-delete retries


def retry_pending_media_deletions(db: Session, now: datetime | None = None, limit: int = 200) -> dict:
    """Retry outbox rows whose time has come, and drop old finished rows from the ledger."""
    now = now or datetime.now(timezone.utc)
    due = db.scalars(
        select(MediaDeletion)
        .where(MediaDeletion.status == STATUS_PENDING)
        .where(or_(MediaDeletion.next_attempt_at.is_(None), MediaDeletion.next_attempt_at <= now))
        .order_by(MediaDeletion.id)
        .limit(limit)
    ).all()
    result = {"attempted": 0, "done": 0, "still_pending": 0, "abandoned": 0}
    for row in due:
        result["attempted"] += 1
        status = media_storage.attempt_deletion(db, row, now)
        key = {"done": "done", "pending": "still_pending", "abandoned": "abandoned"}[status]
        result[key] += 1
    db.flush()
    db.execute(
        sa_delete(MediaDeletion).where(
            MediaDeletion.status == STATUS_DONE,
            MediaDeletion.completed_at < now - timedelta(days=LEDGER_KEEP_DAYS),
        )
    )
    return result


# --------------------------------------------------------------------------- orphan files


def sweep_orphan_files(db: Session, now: datetime | None = None, dry_run: bool = False) -> dict:
    """Remove files under the media directory that no database row references.

    Safeguards: confined to MEDIA_SUBDIRS; a file younger than media_orphan_grace_hours is skipped (it
    may be an upload whose row is not committed yet); a file queued in the outbox counts as referenced;
    and if more than media_orphan_max_per_run orphans turn up the sweep does NOTHING and audits why -
    that pattern means the database and the media directory disagree, which a human must look at."""
    now = now or datetime.now(timezone.utc)
    referenced: set[str] = set()
    for ref in db.scalars(select(CallVoiceNote.secure_object_ref)):
        referenced.add(media_storage.normalise(ref))
    for ref in db.scalars(select(CallRecording.secure_object_ref)):
        if media_storage.is_local_ref(ref):
            referenced.add(media_storage.normalise(ref))
    for ref in db.scalars(
        select(MediaDeletion.secure_object_ref).where(MediaDeletion.status == STATUS_PENDING)
    ):
        referenced.add(media_storage.normalise(ref))

    root = media_storage.media_root()
    cutoff_ts = now.timestamp() - settings.media_orphan_grace_hours * 3600
    orphans = []
    for sub in media_storage.MEDIA_SUBDIRS:
        directory = root / sub
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or media_storage.normalise(path) in referenced:
                continue
            if path.stat().st_mtime > cutoff_ts:
                continue
            orphans.append(path)

    result = {"orphans": len(orphans), "removed": 0, "failed": 0, "aborted": False, "dry_run": dry_run}
    if dry_run or not orphans:
        return result
    if len(orphans) > settings.media_orphan_max_per_run:
        result["aborted"] = True
        audit.record(
            db, action="media.orphan_sweep_aborted", entity_type="media_dir",
            after={"found": len(orphans), "limit": settings.media_orphan_max_per_run},
        )
        logger.error(
            "orphan sweep aborted: %s unreferenced files exceeds the limit of %s",
            len(orphans), settings.media_orphan_max_per_run,
        )
        return result
    for path in sorted(orphans):
        age_hours = int((now.timestamp() - path.stat().st_mtime) // 3600)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            result["failed"] += 1
            audit.record(
                db, action="media.orphan_remove_failed", entity_type="media_file",
                after={"file": path.name, "error": f"{type(exc).__name__}: {exc}"[:300]},
            )
            continue
        result["removed"] += 1
        audit.record(
            db, action="media.orphan_removed", entity_type="media_file",
            after={"file": path.name, "age_hours": age_hours},
        )
    return result


# --------------------------------------------------------------------------- nightly entry point


def run_nightly(db: Session, now: datetime | None = None) -> dict:
    """All retention steps, each committed (or rolled back) on its own."""
    summary: dict = {}

    def step(name: str, fn):
        try:
            summary[name] = fn()
            db.commit()
        except Exception:  # noqa: BLE001 - one failing step must not block the rest
            db.rollback()
            logger.exception("retention step %s failed", name)
            summary[name] = "failed"

    step("rm_audio_purged", lambda: purge_expired_rm_audio(db, now))
    step("media_deletions", lambda: retry_pending_media_deletions(db, now))
    step("orphan_files", lambda: sweep_orphan_files(db, now))
    step("commitments", lambda: commitments_svc.apply_lifecycle(db, now))
    logger.info("retention: %s", summary)
    return summary
