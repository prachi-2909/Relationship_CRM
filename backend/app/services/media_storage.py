"""Local disk storage for uploaded call media (DC voice notes today).
Every caller only ever deals in a secure_object_ref string, so swapping this
for real object storage later is purely a config/implementation change here.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import Session

from ..config import get_settings

settings = get_settings()


def _root() -> Path:
    db_path = None
    if settings.database_url.startswith("sqlite"):
        _, _, path_part = settings.database_url.partition(":///")
        if path_part and path_part != ":memory:":
            db_path = Path(path_part)
    base = db_path.parent if db_path else Path(".")
    return base / settings.media_dir


def save_upload(subdir: str, filename: str, data: bytes) -> str:
    """Saves bytes under media_dir/subdir with a random name, returns the
    path to store as secure_object_ref."""
    root = _root() / subdir
    root.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix or ".bin"
    dest = root / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(data)
    return str(dest)


def delete(secure_object_ref: str) -> None:
    """Removes a previously saved file. A missing file is not an error - the
    DB row being gone is what matters to callers."""
    Path(secure_object_ref).unlink(missing_ok=True)


_PENDING_DELETES_KEY = "media_storage.pending_deletes"


def delete_after_commit(db: Session, secure_object_ref: str) -> None:
    """Deletes the file only once the transaction that dropped its row commits.
    Deleting first and then failing to commit would leave a row pointing at a
    file that no longer exists; a rollback here simply keeps both."""
    if not event.contains(db, "after_commit", _flush_pending_deletes):
        event.listen(db, "after_commit", _flush_pending_deletes)
        event.listen(db, "after_rollback", _drop_pending_deletes)
    db.info.setdefault(_PENDING_DELETES_KEY, []).append(secure_object_ref)


def _flush_pending_deletes(db: Session) -> None:
    for ref in db.info.pop(_PENDING_DELETES_KEY, []):
        delete(ref)


def _drop_pending_deletes(db: Session) -> None:
    db.info.pop(_PENDING_DELETES_KEY, None)
