"""The single entry point for writing audit rows.

Every state-changing operation calls ``record(...)`` before its ``db.commit()``.
"""

from typing import Any

from sqlalchemy.orm import Session

from ..models.audit import AuditLog


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: Any | None = None,
    actor_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
    )
    db.add(entry)
    db.flush()
    return entry
