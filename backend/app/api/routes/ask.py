"""The Supervisor: one endpoint that answers a free-text question over the
relationships and stakeholder graph already on record, remembering the
running conversation so a follow-up ("what about his stakeholders?") can be
resolved against what was just discussed. Read-only, no send path - a human
decides what to do with the answer."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.user import User
from ...schemas.ask import AskRequest, AskResponse, ConversationDetail, ConversationSummary
from ...security.deps import get_current_user
from ...services import conversations, supervisor

router = APIRouter(prefix="/ask", tags=["supervisor"])


@router.post("", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    conv = conversations.get_or_create(db, actor, payload.conversation_id)
    # a fresh conversation is already flushed (has an id) with no messages
    # yet, so this naturally returns [] for it - no special-casing needed
    history_rows = conversations.recent_messages(db, conv.id)
    history = [{"role": m.role.value, "content": m.content} for m in history_rows]
    prior_considered = conversations.last_considered(history_rows)

    result = supervisor.answer(
        db, actor, payload.question, history=history, prior_considered=prior_considered
    )

    conversations.append_turn(
        db,
        conv,
        question=payload.question,
        answer=result["answer"],
        scope=result["scope"],
        generated_by=result["generated_by"],
        considered=result["considered"],
    )
    db.commit()
    return AskResponse(conversation_id=conv.id, **result)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return conversations.list_for_user(db, actor, limit=limit)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    conv = conversations.get_detail(db, actor, conversation_id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=list(conv.messages),
    )
