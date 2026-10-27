"""Local disk storage for uploaded call media (DC voice notes today).
Every caller only ever deals in a secure_object_ref string, so swapping this
for real object storage later is purely a config/implementation change here.

Deletion goes through an outbox (see models/media_deletion.py): the intent to delete is written in the
same transaction that drops the database row, the file is removed after commit, and a failure is
retried with backoff and finally abandoned loudly - never silently lost.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.media_deletion import (
    STATUS_ABANDONED,
    STATUS_DONE,
    STATUS_PENDING,
    MediaDeletion,
)

logger = logging.getLogger("rcrm.media")
settings = get_settings()

# The only sub-directories save_upload writes to. The orphan sweep is confined to these, so a new,
# unrelated directory under the media root is never swept by accident.
MEDIA_SUBDIRS = ("voice_notes",)


def _root() -> Path:
    db_path = None
    if settings.database_url.startswith("sqlite"):
        _, _, path_part = settings.database_url.partition(":///")
        if path_part and path_part != ":memory:":
            db_path = Path(path_part)
    base = db_path.parent if db_path else Path(".")
    return base / settings.media_dir


def media_root() -> Path:
    return _root()


def save_upload(subdir: str, filename: str, data: bytes) -> str:
    """Saves bytes under media_dir/subdir with a random name, returns the
    path to store as secure_object_ref."""
    root = _root() / subdir
    root.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix or ".bin"
    dest = root / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(data)
    return str(dest)


class MediaDeleteError(Exception):
    """A deletion that must not be retried (it can never succeed, or it would be unsafe)."""


def is_local_ref(ref: str | None) -> bool:
    """True for a file path we stored; False for a provider URL, which is not ours to delete."""
    return bool(ref) and not ref.lower().startswith(("http://", "https://"))


def normalise(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def is_inside_root(ref: str | Path) -> bool:
    try:
        Path(normalise(ref)).relative_to(Path(normalise(_root())))
    except ValueError:
        return False
    return True


def delete(secure_object_ref: str) -> None:
    """Removes a previously saved file. A missing file is not an error - the DB row being gone is what
    matters. Refuses anything that is not a file inside the media root (a URL, or a path from a
    tampered/odd row), raising MediaDeleteError; an OSError (e.g. a locked file) is left to propagate
    so the caller can retry."""
    if not is_local_ref(secure_object_ref) or not is_inside_root(secure_object_ref):
        raise MediaDeleteError("refusing to delete a path outside the media root")
    Path(secure_object_ref).unlink(missing_ok=True)


def _backoff(attempts: int) -> timedelta:
    # 5 min, 10, 20, 40 ... capped at a day.
    return timedelta(minutes=min(5 * 2 ** max(attempts - 1, 0), 24 * 60))


def attempt_deletion(s: Session, row: MediaDeletion, now: datetime | None = None) -> str:
    """Carry out one outbox row and record the outcome (and an audit entry for anything that is not a
    clean first-time success). Returns the row's new status."""
    from . import audit

    now = now or datetime.now(timezone.utc)
    name = Path(row.secure_object_ref).name  # the file name only - never the full path - goes into audit
    try:
        delete(row.secure_object_ref)
    except MediaDeleteError as exc:
        row.status = STATUS_ABANDONED
        row.last_error = str(exc)[:300]
        row.completed_at = now
        audit.record(
            s, action="media.delete_abandoned", entity_type="media_deletion", entity_id=row.id,
            after={"file": name, "reason": row.reason, "error": row.last_error, "permanent": True},
        )
        return row.status
    except OSError as exc:
        row.attempts += 1
        row.last_error = f"{type(exc).__name__}: {exc}"[:300]
        if row.attempts >= settings.media_delete_max_attempts:
            row.status = STATUS_ABANDONED
            row.completed_at = now
            row.next_attempt_at = None
            audit.record(
                s, action="media.delete_abandoned", entity_type="media_deletion", entity_id=row.id,
                after={"file": name, "reason": row.reason, "attempts": row.attempts, "error": row.last_error},
            )
        else:
            row.next_attempt_at = now + _backoff(row.attempts)
            audit.record(
                s, action="media.delete_failed", entity_type="media_deletion", entity_id=row.id,
                after={"file": name, "reason": row.reason, "attempt": row.attempts,
                       "next_attempt_at": row.next_attempt_at.isoformat(), "error": row.last_error},
            )
        return row.status

    retried = row.attempts > 0
    row.status = STATUS_DONE
    row.completed_at = now
    row.last_error = None
    row.next_attempt_at = None
    if retried:
        audit.record(
            s, action="media.delete_retried_ok", entity_type="media_deletion", entity_id=row.id,
            after={"file": name, "reason": row.reason, "attempts": row.attempts},
        )
    return row.status


_PENDING_DELETES_KEY = "media_storage.pending_deletes"


def delete_after_commit(db: Session, secure_object_ref: str, reason: str = "retention") -> None:
    """Queue a file for deletion, to be carried out only once the transaction that dropped its row
    commits. The outbox row is part of that same transaction, so a rollback discards the intent and the
    file survives; a crash after the commit leaves a pending row the nightly retry picks up."""
    db.add(
        MediaDeletion(
            secure_object_ref=secure_object_ref,
            reason=reason,
            status=STATUS_PENDING,
            attempts=0,
            next_attempt_at=datetime.now(timezone.utc),
        )
    )
    if not event.contains(db, "after_commit", _flush_pending_deletes):
        event.listen(db, "after_commit", _flush_pending_deletes)
        event.listen(db, "after_rollback", _drop_pending_deletes)
    db.info.setdefault(_PENDING_DELETES_KEY, []).append(secure_object_ref)


def _flush_pending_deletes(db: Session) -> None:
    refs = db.info.pop(_PENDING_DELETES_KEY, [])
    if not refs:
        return
    # A fresh short session: the committed one is no longer usable for writes here. Any failure is
    # swallowed on purpose - the rows stay pending and the nightly retry handles them - because the
    # caller's commit has already succeeded and must not appear to fail.
    try:
        with Session(bind=db.get_bind()) as s:
            for ref in refs:
                row = s.scalar(
                    select(MediaDeletion)
                    .where(MediaDeletion.secure_object_ref == ref, MediaDeletion.status == STATUS_PENDING)
                    .order_by(MediaDeletion.id.desc())
                    .limit(1)
                )
                if row is not None:
                    attempt_deletion(s, row)
            s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("post-commit media deletion bookkeeping failed; will be retried by the sweep")


def _drop_pending_deletes(db: Session) -> None:
    db.info.pop(_PENDING_DELETES_KEY, None)
