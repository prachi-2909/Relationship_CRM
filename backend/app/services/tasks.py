"""Task creation — shared by the tasks API route and the agent's approval path,
so a recommendation is approved by calling the exact same logic a human-created
task goes through, not a duplicate of it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models.relationship import Relationship
from ..models.task import Task, TaskStatus
from . import audit, scoring


def create_task(
    db: Session,
    *,
    relationship: Relationship,
    title: str,
    detail: str | None = None,
    due_at: datetime | None = None,
    assigned_to: int | None = None,
    source_interaction_id: int | None = None,
    actor_id: int | None,
) -> Task:
    resolved_assignee = assigned_to if assigned_to is not None else relationship.owner_id

    task = Task(
        relationship_id=relationship.id,
        official_id=relationship.official_id,
        title=title,
        detail=detail,
        due_at=due_at,
        assigned_to=resolved_assignee,
        source_interaction_id=source_interaction_id,
        created_by=actor_id,
        status=TaskStatus.OPEN,
    )
    db.add(task)
    db.flush()
    scoring.recompute_and_store(db, relationship, reason="task created")
    audit.record(
        db,
        action="task.create",
        entity_type="task",
        entity_id=task.id,
        actor_id=actor_id,
        after={"relationship_id": relationship.id, "title": task.title},
    )
    return task
