"""RAG maintenance: a manual, admin-only reindex - not a background worker."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.user import Role, User
from ...security.deps import require_roles
from ...services import knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/reindex")
def reindex(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    count = knowledge.reindex_all(db)
    db.commit()
    return {"indexed": count}
