"""Device attestation: issue a challenge, verify the Android hardware Key Attestation chain.

Report-only unless settings.require_device_attestation (see key_attestation.py). The DC app calls
these after login; a failed/again-unverified device is audited, and only blocked once enforcement is
switched on after real-device validation.
"""

import base64

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.user import User
from ...security import key_attestation
from ...security.deps import get_current_user
from ...services import audit

settings = get_settings()
router = APIRouter(prefix="/auth/attest", tags=["attestation"])


class ChallengeResponse(BaseModel):
    challenge: str


class AttestationRequest(BaseModel):
    challenge: str
    # Leaf-first certificate chain, each cert base64-encoded DER.
    certificates: list[str]


class AttestationResponse(BaseModel):
    attested: bool
    enforced: bool
    reason: str


@router.post("/challenge", response_model=ChallengeResponse)
def challenge(actor: User = Depends(get_current_user)):
    return ChallengeResponse(challenge=key_attestation.new_challenge())


@router.post("/verify", response_model=AttestationResponse)
def verify(
    payload: AttestationRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    try:
        chain = [base64.b64decode(c) for c in payload.certificates]
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Malformed certificate encoding") from exc

    result = key_attestation.verify(chain, payload.challenge)
    audit.record(
        db, action="auth.device_attestation", entity_type="user", entity_id=actor.id,
        actor_id=actor.id,
        after={"attested": result.verified, "reason": result.reason,
               "verified_boot": result.verified_boot, "enforced": settings.require_device_attestation},
    )
    db.commit()

    # Enforcement is opt-in; until then a failed verdict is recorded but the device is allowed.
    if settings.require_device_attestation and not result.verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Device failed attestation: {result.reason}")

    return AttestationResponse(
        attested=result.verified, enforced=settings.require_device_attestation, reason=result.reason
    )
