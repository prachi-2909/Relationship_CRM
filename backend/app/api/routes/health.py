"""Liveness + database reachability. No auth."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...db import get_db
from ...services import backup

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    last_backup = backup.last_backup_at()
    return {
        "status": "ok" if db_ok else "degraded",
        "time": datetime.now(timezone.utc).isoformat(),
        "database": db_ok,
        "last_backup_at": last_backup.isoformat() if last_backup else None,
    }
