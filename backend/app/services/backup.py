"""Automated SQLite backups, using sqlite3's own online backup API.

Not wired to any non-SQLite database - Postgres backup/recovery is an
operator/infra concern, not application code, and this codebase is
SQLite-only for now (see config.is_sqlite).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings

logger = logging.getLogger("rcrm.backup")

_FILE_PREFIX = "relationship_crm-"


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite"):
        return None
    _, _, path_part = database_url.partition(":///")
    if not path_part or path_part == ":memory:":
        return None
    return Path(path_part)


def create_backup(*, database_url: str | None = None) -> Path | None:
    """Snapshot the live database. Returns the backup path, or None if skipped."""
    settings = get_settings()
    src_path = _sqlite_path(database_url or settings.database_url)
    if src_path is None:
        logger.warning("backup skipped: not a file-backed sqlite database")
        return None
    if not src_path.exists():
        logger.warning("backup skipped: database file not found (%s)", src_path)
        return None

    backup_root = src_path.parent / settings.backup_dir
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_path = backup_root / f"{_FILE_PREFIX}{stamp}.db"

    src_conn = sqlite3.connect(str(src_path))
    try:
        dest_conn = sqlite3.connect(str(dest_path))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    _prune_old_backups(backup_root, settings.backup_retention_count)
    logger.info("backup created: %s", dest_path)
    return dest_path


def _prune_old_backups(backup_root: Path, retention: int) -> None:
    backups = sorted(backup_root.glob(f"{_FILE_PREFIX}*.db"))
    excess = len(backups) - retention
    for stale in backups[: max(excess, 0)]:
        stale.unlink(missing_ok=True)


def last_backup_at(*, database_url: str | None = None) -> datetime | None:
    """Timestamp of the most recent backup on disk, or None if there isn't one."""
    settings = get_settings()
    src_path = _sqlite_path(database_url or settings.database_url)
    if src_path is None:
        return None
    backup_root = src_path.parent / settings.backup_dir
    backups = sorted(backup_root.glob(f"{_FILE_PREFIX}*.db")) if backup_root.exists() else []
    if not backups:
        return None
    return datetime.fromtimestamp(backups[-1].stat().st_mtime, tz=timezone.utc)
