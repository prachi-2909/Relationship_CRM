"""Request/response models for tasks and follow-ups."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.task import TaskStatus


class TaskCreate(BaseModel):
    relationship_id: int
    title: str = Field(min_length=1, max_length=300)
    detail: str | None = None
    due_at: datetime | None = None
    assigned_to: int | None = None
    source_interaction_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    detail: str | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None
    assigned_to: int | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relationship_id: int
    official_id: int
    official_name: str
    title: str
    detail: str | None
    due_at: datetime | None
    status: TaskStatus
    assigned_to: int | None
    source_interaction_id: int | None
    completed_at: datetime | None
    escalated_at: datetime | None
    created_at: datetime

    @staticmethod
    def of(task) -> "TaskOut":
        return TaskOut(
            id=task.id,
            relationship_id=task.relationship_id,
            official_id=task.official_id,
            official_name=task.relationship_ref.official.name,
            title=task.title,
            detail=task.detail,
            due_at=task.due_at,
            status=task.status,
            assigned_to=task.assigned_to,
            source_interaction_id=task.source_interaction_id,
            completed_at=task.completed_at,
            escalated_at=task.escalated_at,
            created_at=task.created_at,
        )


class TaskListResponse(BaseModel):
    items: list[TaskOut]
    total: int
    limit: int
    offset: int
