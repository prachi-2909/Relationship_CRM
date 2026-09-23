from datetime import datetime, timezone

from app.models.call_intelligence import CallSession, CallSessionStatus, IdentityStatus
from app.models.interaction import Direction
from app.models.relationship import Relationship


def test_call_session_defaults(db, make_official, make_user):
    official = make_official(name="Call Model Target")
    user = make_user(email="dcuser@example.com")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    db.refresh(rel)

    call = CallSession(
        dc_user_id=user.id,
        direction=Direction.OUTBOUND,
        phone_ref="9876543210",
        started_at=datetime.now(timezone.utc),
        official_id=official.id,
        relationship_id=rel.id,
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    assert call.recording_status == CallSessionStatus.INITIATED
    assert call.identity_status == IdentityStatus.UNREGISTERED
    assert call.processing_status == CallSessionStatus.INITIATED
    assert call.interaction_id is None


def test_call_session_status_enum_covers_full_state_machine():
    values = {s.value for s in CallSessionStatus}
    for expected in (
        "initiated", "ringing", "connected", "ended", "recording", "no_recording",
        "upload_pending", "uploaded", "transcribing", "analyzing", "review_required",
        "approved", "crm_logged", "cancelled", "recording_unavailable",
        "upload_failed", "transcription_failed", "analysis_failed",
        "review_rejected", "crm_write_failed",
    ):
        assert expected in values
