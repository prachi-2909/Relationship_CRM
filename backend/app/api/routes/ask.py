"""The Supervisor: one endpoint that answers a free-text question over the
relationships and stakeholder graph already on record. Read-only, no send
path - a human decides what to do with the answer."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.user import User
from ...schemas.ask import AskRequest, AskResponse
from ...security.deps import get_current_user
from ...services import supervisor

router = APIRouter(prefix="/ask", tags=["supervisor"])


@router.post("", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return supervisor.answer(db, actor, payload.question)
