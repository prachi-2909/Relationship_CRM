"""Persistence for Supervisor conversations - the plumbing behind /ask's
short-term memory. Routing/synthesis logic stays in ``supervisor``; this
module only owns loading, appending, and scoping conversations to their
owner.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.conversation import AskConversation, AskMessage, MessageRole
from ..models.user import User

HISTORY_LIMIT = 10  # messages (~5 turns) kept in the prompt - enough context,
# small enough to stay cheap and keep the model focused on the recent thread


def _load_owned(db: Session, actor: User, conversation_id: int) -> AskConversation:
    conv = db.get(AskConversation, conversation_id)
    if conv is None or conv.user_id != actor.id:
        # 404, not 403: don't confirm another user's conversation exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


def get_or_create(db: Session, actor: User, conversation_id: int | None) -> AskConversation:
    if conversation_id is not None:
        return _load_owned(db, actor, conversation_id)
    conv = AskConversation(user_id=actor.id)
    db.add(conv)
    db.flush()
    return conv


def get_detail(db: Session, actor: User, conversation_id: int) -> AskConversation:
    return _load_owned(db, actor, conversation_id)


def list_for_user(db: Session, actor: User, *, limit: int = 20) -> list[AskConversation]:
    return list(
        db.scalars(
            select(AskConversation)
            .where(AskConversation.user_id == actor.id)
            .order_by(AskConversation.updated_at.desc())
            .limit(limit)
        )
    )


def recent_messages(db: Session, conversation_id: int, *, limit: int = HISTORY_LIMIT) -> list[AskMessage]:
    rows = db.scalars(
        select(AskMessage)
        .where(AskMessage.conversation_id == conversation_id)
        .order_by(AskMessage.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def last_considered(messages: list[AskMessage]) -> list[dict] | None:
    """The ``considered`` list from the most recent assistant turn, if any -
    the candidate subject for a pronoun-style follow-up question."""
    for m in reversed(messages):
        if m.role is MessageRole.ASSISTANT and m.considered:
            return m.considered
    return None


def append_turn(
    db: Session,
    conv: AskConversation,
    *,
    question: str,
    answer: str,
    scope: str,
    generated_by: str,
    considered: list[dict],
) -> None:
    if conv.title is None:
        conv.title = question[:200]
    db.add(AskMessage(conversation_id=conv.id, role=MessageRole.USER, content=question))
    db.add(
        AskMessage(
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            scope=scope,
            generated_by=generated_by,
            considered=considered,
        )
    )
    # appending a child message doesn't touch the parent row on its own -
    # bump it explicitly so "most recently active" sorting is correct
    conv.updated_at = datetime.now(timezone.utc)
    db.flush()
