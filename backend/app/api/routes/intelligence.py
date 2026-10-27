"""Quality of the relationship intelligence, measured from explicit human decisions only."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.user import Role, User
from ...security.deps import require_roles
from ...services import intelligence_feedback as feedback_svc

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

_VIEWERS = require_roles(Role.ADMIN, Role.APPROVER_VIEWER)


@router.get("/quality")
def quality(db: Session = Depends(get_db), _: User = Depends(_VIEWERS)):
    """How good the suggestions are: usefulness ratings per kind, proposal acceptance, commitment
    fulfilment and duplicate-flag precision. A rate is withheld until there are enough decisions behind
    it; only explicit human actions are counted - never an interaction merely having happened."""
    return feedback_svc.quality_metrics(db)
