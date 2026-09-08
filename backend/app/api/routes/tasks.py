"""Tasks and follow-ups: create, complete, and the overdue sweep."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.interaction import Interaction
from ...models.relationship import Relationship
from ...models.task import Task, TaskStatus
from ...models.user import Role, User
from ...schemas.task import TaskCreate, TaskListResponse, TaskOut, TaskUpdate
from ...scheduler import sweep_overdue_tasks
from ...security.deps import get_current_user, require_roles
from ...services import audit, scoring

router = APIRouter(prefix="/tasks", tags=["tasks"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)
_SORTABLE = {
    "due_at": Task.due_at,
    "-due_at": Task.due_at.desc(),
    "created_at": Task.created_at,
    "-created_at": Task.created_at.desc(),
}


def _load(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@router.get("", response_model=TaskListResponse)
def list_tasks(
    relationship_id: int | None = None,
    official_id: int | None = None,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    overdue: bool = False,
    mine: bool = False,
    assigned_to: int | None = None,
    sort: str = "due_at",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if sort not in _SORTABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown sort key")

    filters = []
    if relationship_id is not None:
        filters.append(Task.relationship_id == relationship_id)
    if official_id is not None:
        filters.append(Task.official_id == official_id)
    if status_filter is not None:
        filters.append(Task.status == status_filter)
    if mine:
        filters.append(Task.assigned_to == user.id)
    elif assigned_to is not None:
        filters.append(Task.assigned_to == assigned_to)
    if overdue:
        filters.append(Task.status == TaskStatus.OPEN)
        filters.append(Task.due_at.is_not(None))
        filters.append(Task.due_at < datetime.now(timezone.utc))

    total = db.scalar(select(func.count()).select_from(Task).where(*filters)) or 0
    rows = db.scalars(
        select(Task).where(*filters).order_by(_SORTABLE[sort]).limit(limit).offset(offset)
    ).all()
    return TaskListResponse(
        items=[TaskOut.of(t) for t in rows], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rel = db.get(Relationship, payload.relationship_id)
    if rel is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Relationship not found")
    if payload.source_interaction_id is not None:
        src = db.get(Interaction, payload.source_interaction_id)
        if src is None or src.relationship_id != rel.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Source interaction mismatch"
            )
    assigned_to = payload.assigned_to if payload.assigned_to is not None else rel.owner_id
    if assigned_to is not None and db.get(User, assigned_to) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Assignee not found")

    task = Task(
        relationship_id=rel.id,
        official_id=rel.official_id,
        title=payload.title,
        detail=payload.detail,
        due_at=payload.due_at,
        assigned_to=assigned_to,
        source_interaction_id=payload.source_interaction_id,
        created_by=actor.id,
        status=TaskStatus.OPEN,
    )
    db.add(task)
    db.flush()
    scoring.recompute_and_store(db, rel, reason="task created")
    audit.record(
        db,
        action="task.create",
        entity_type="task",
        entity_id=task.id,
        actor_id=actor.id,
        after={"relationship_id": rel.id, "title": task.title},
    )
    db.commit()
    db.refresh(task)
    return TaskOut.of(task)


@router.get("/overdue", response_model=TaskListResponse)
def overdue_tasks(
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    filters = [
        Task.status == TaskStatus.OPEN,
        Task.due_at.is_not(None),
        Task.due_at < now,
    ]
    total = db.scalar(select(func.count()).select_from(Task).where(*filters)) or 0
    rows = db.scalars(
        select(Task).where(*filters).order_by(Task.due_at).limit(limit)
    ).all()
    return TaskListResponse(items=[TaskOut.of(t) for t in rows], total=total, limit=limit, offset=0)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return TaskOut.of(_load(db, task_id))


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    task = _load(db, task_id)
    data = payload.model_dump(exclude_unset=True)

    if data.get("assigned_to") is not None and db.get(User, data["assigned_to"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Assignee not found")

    status_changed = "status" in data and data["status"] != task.status
    for key in ("title", "detail", "due_at", "assigned_to", "status"):
        if key in data:
            setattr(task, key, data[key])

    if status_changed:
        if task.status is TaskStatus.DONE:
            task.completed_at = datetime.now(timezone.utc)
        else:
            task.completed_at = None
        if task.status is not TaskStatus.OPEN:
            task.escalated_at = None
        db.flush()
        scoring.recompute_and_store(
            db, task.relationship_ref, reason="task status changed"
        )

    audit.record(
        db,
        action="task.update",
        entity_type="task",
        entity_id=task.id,
        actor_id=actor.id,
        after={k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in data.items()},
    )
    db.commit()
    db.refresh(task)
    return TaskOut.of(task)


@router.post("/run-overdue-sweep")
def run_overdue_sweep(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    escalated = sweep_overdue_tasks(db)
    db.commit()
    return {"escalated": escalated}
