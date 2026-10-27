"""Retention: RM audio purge (audio only), the deletion outbox (audit, retries, abandon), orphan-file
cleanup, commitment/memory lifecycle - and that the DC flow and access controls are unchanged."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.call_intelligence import (
    CallAIAnalysis,
    CallSession,
    CallSessionStatus,
    CallTranscript,
    CallVoiceNote,
)
from app.models.commitment import Commitment, CommitmentParty, CommitmentSourceKind, CommitmentStatus
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.media_deletion import STATUS_ABANDONED, STATUS_DONE, STATUS_PENDING, MediaDeletion
from app.models.user import Role
from app.services import call_intelligence as call_svc
from app.services import commitments as commitments_svc
from app.services import media_storage, precall, retention

NOW = datetime.now(timezone.utc)


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage.settings, "media_dir", str(tmp_path))
    return tmp_path


def _audits(db, action):
    return [a for a in db.query(AuditLog).all() if a.action == action]


def _call_with_audio(db, user, *, age_days, transcript=True, brief=False):
    call = CallSession(
        dc_user_id=user.id, direction=Direction.OUTBOUND, phone_ref="9000000003", started_at=NOW,
    )
    db.add(call)
    db.commit()
    call_svc.submit_voice_note(db, call, audio_bytes=b"audio-bytes", filename="n.m4a", actor=user)
    db.commit()
    path = Path(call.voice_note.secure_object_ref)
    note = db.scalar(select(CallVoiceNote).where(CallVoiceNote.call_session_id == call.id))
    note.created_at = NOW - timedelta(days=age_days)
    if transcript:
        db.add(CallTranscript(call_session_id=call.id, source_type="voice_note", provider="x", text="hello world"))
    if brief:
        db.add(CallAIAnalysis(call_session_id=call.id, analysis_json={"summary": "kept"}))
    db.commit()
    return call, path


def _age_file(path: Path, hours: float):
    t = NOW.timestamp() - hours * 3600
    os.utime(path, (t, t))


# --------------------------------------------------------------------------- RM audio: 60 days, audio only


def test_default_rm_retention_is_60_days():
    assert media_storage.settings.rm_recording_retention_days == 60


def test_rm_audio_past_60_days_is_deleted_but_transcript_and_brief_stay(db, media, make_user):
    rm = make_user(email="rm-ret1@example.com", role=Role.RELATIONSHIP_MANAGER)
    call, path = _call_with_audio(db, rm, age_days=61, transcript=True, brief=True)
    assert path.exists()

    assert retention.purge_expired_rm_audio(db) == 1
    db.commit()
    db.expire_all()

    assert not path.exists()                                                            # file gone
    assert db.scalar(select(CallVoiceNote).where(CallVoiceNote.call_session_id == call.id)) is None
    assert db.scalar(select(CallTranscript).where(CallTranscript.call_session_id == call.id)).text == "hello world"
    assert db.scalar(select(CallAIAnalysis).where(CallAIAnalysis.call_session_id == call.id)) is not None
    assert db.get(CallSession, call.id).recording_status == CallSessionStatus.PURGED


def test_rm_audio_inside_the_window_is_kept(db, media, make_user):
    rm = make_user(email="rm-ret2@example.com", role=Role.RELATIONSHIP_MANAGER)
    young, young_path = _call_with_audio(db, rm, age_days=59)
    old, old_path = _call_with_audio(db, rm, age_days=61)
    assert retention.purge_expired_rm_audio(db) == 1
    db.commit()
    assert young_path.exists() and not old_path.exists()


def test_rm_purge_never_touches_dc_audio(db, media, make_user):
    dc = make_user(email="dc-ret3@example.com", role=Role.DC)
    _, path = _call_with_audio(db, dc, age_days=400)
    assert retention.purge_expired_rm_audio(db) == 0
    db.commit()
    assert path.exists()


def test_dc_unlogged_purge_still_works_and_still_ignores_rm_audio(db, media, make_user):
    dc = make_user(email="dc-ret4@example.com", role=Role.DC)
    rm = make_user(email="rm-ret4@example.com", role=Role.RELATIONSHIP_MANAGER)
    _, dc_old = _call_with_audio(db, dc, age_days=8)
    _, dc_young = _call_with_audio(db, dc, age_days=3)
    _, rm_old = _call_with_audio(db, rm, age_days=100)
    assert call_svc.purge_stale_call_audio(db) == 1     # the existing 7-day DC policy, unchanged
    db.commit()
    assert not dc_old.exists() and dc_young.exists() and rm_old.exists()


def test_rm_purge_is_audited_without_paths_or_text(db, media, make_user):
    rm = make_user(email="rm-ret5@example.com", role=Role.RELATIONSHIP_MANAGER)
    call, path = _call_with_audio(db, rm, age_days=70)
    retention.purge_expired_rm_audio(db)
    db.commit()
    (entry,) = _audits(db, "call.audio_purged_retention_expired")
    assert entry.entity_id == str(call.id)
    assert entry.after["scope"] == "audio_only" and entry.after["transcript_retained"] is True
    assert entry.after["had_transcript"] is True and entry.after["retention_days"] == 60
    assert str(path) not in str(entry.after) and "hello world" not in str(entry.after)


def test_rm_purge_is_idempotent_and_dry_run_deletes_nothing(db, media, make_user):
    rm = make_user(email="rm-ret6@example.com", role=Role.RELATIONSHIP_MANAGER)
    _, path = _call_with_audio(db, rm, age_days=90)
    assert retention.purge_expired_rm_audio(db, dry_run=True) == 1
    db.commit()
    assert path.exists() and not _audits(db, "call.audio_purged_retention_expired")
    assert retention.purge_expired_rm_audio(db) == 1
    db.commit()
    assert retention.purge_expired_rm_audio(db) == 0    # second run: nothing left to do
    assert len(_audits(db, "call.audio_purged_retention_expired")) == 1


# --------------------------------------------------------------------------- deletion outbox


def _pending_rows(db):
    db.expire_all()
    return db.query(MediaDeletion).all()


def test_successful_delete_is_recorded_in_the_ledger(db, media, make_user):
    rm = make_user(email="rm-ob1@example.com", role=Role.RELATIONSHIP_MANAGER)
    _, path = _call_with_audio(db, rm, age_days=61)
    retention.purge_expired_rm_audio(db)
    db.commit()
    (row,) = _pending_rows(db)
    assert row.status == STATUS_DONE and row.reason == "rm_retention_expired" and row.attempts == 0
    assert not path.exists()


def test_failed_delete_is_queued_then_retried_with_backoff_and_audited(db, media, make_user, monkeypatch):
    rm = make_user(email="rm-ob2@example.com", role=Role.RELATIONSHIP_MANAGER)
    _, path = _call_with_audio(db, rm, age_days=61)
    real_delete = media_storage.delete

    def locked(_ref):
        raise PermissionError("file is locked")

    monkeypatch.setattr(media_storage, "delete", locked)
    retention.purge_expired_rm_audio(db)
    db.commit()                                   # the row is gone, the file could not be deleted
    (row,) = _pending_rows(db)
    assert path.exists()
    assert row.status == STATUS_PENDING and row.attempts == 1 and "locked" in row.last_error
    assert len(_audits(db, "media.delete_failed")) == 1

    # not yet due: backoff is respected
    assert retention.retry_pending_media_deletions(db, now=datetime.now(timezone.utc))["attempted"] == 0

    monkeypatch.setattr(media_storage, "delete", real_delete)
    result = retention.retry_pending_media_deletions(db, now=datetime.now(timezone.utc) + timedelta(minutes=6))
    db.commit()
    assert result["done"] == 1
    (row,) = _pending_rows(db)
    assert row.status == STATUS_DONE and row.attempts == 1 and not path.exists()
    assert len(_audits(db, "media.delete_retried_ok")) == 1


def test_a_deletion_that_keeps_failing_is_abandoned_and_audited(db, media, make_user, monkeypatch):
    monkeypatch.setattr(media_storage.settings, "media_delete_max_attempts", 2)
    rm = make_user(email="rm-ob3@example.com", role=Role.RELATIONSHIP_MANAGER)
    _, path = _call_with_audio(db, rm, age_days=61)

    def locked(_ref):
        raise PermissionError("still locked")

    monkeypatch.setattr(media_storage, "delete", locked)
    retention.purge_expired_rm_audio(db)
    db.commit()
    later = datetime.now(timezone.utc) + timedelta(hours=1)
    result = retention.retry_pending_media_deletions(db, now=later)
    db.commit()
    assert result["abandoned"] == 1
    (row,) = _pending_rows(db)
    assert row.status == STATUS_ABANDONED and row.attempts == 2
    assert len(_audits(db, "media.delete_abandoned")) == 1
    # an abandoned row is not retried forever
    assert retention.retry_pending_media_deletions(db, now=later + timedelta(days=3))["attempted"] == 0
    assert path.exists()   # still on disk - and now flagged for an operator, not silently lost


def test_a_path_outside_the_media_root_is_refused_and_never_deleted(db, media, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "precious.txt"
    outside.write_text("do not delete")
    media_storage.delete_after_commit(db, str(outside), reason="test")
    db.commit()
    (row,) = _pending_rows(db)
    assert row.status == STATUS_ABANDONED and "outside the media root" in row.last_error
    assert outside.exists()
    assert len(_audits(db, "media.delete_abandoned")) == 1


def test_a_provider_url_is_never_treated_as_a_file(db, media, make_user):
    assert media_storage.is_local_ref("https://provider.example/rec/1.mp3") is False
    with pytest.raises(media_storage.MediaDeleteError):
        media_storage.delete("https://provider.example/rec/1.mp3")


def test_rolled_back_transaction_keeps_the_file_and_leaves_no_queue_row(db, media):
    f = media_storage.save_upload("voice_notes", "x.m4a", b"x")
    media_storage.delete_after_commit(db, f)
    db.rollback()
    assert Path(f).exists() and _pending_rows(db) == []


# --------------------------------------------------------------------------- orphan files


def _orphan(name_bytes=b"o"):
    p = Path(media_storage.save_upload("voice_notes", "orphan.m4a", name_bytes))
    return p


def test_old_unreferenced_file_is_removed_and_audited(db, media):
    p = _orphan()
    _age_file(p, 48)
    result = retention.sweep_orphan_files(db)
    db.commit()
    assert result["removed"] == 1 and not p.exists()
    (entry,) = _audits(db, "media.orphan_removed")
    assert entry.after["file"] == p.name and str(p.parent) not in str(entry.after)


def test_referenced_young_and_queued_files_are_never_swept(db, media, make_user):
    rm = make_user(email="rm-or1@example.com", role=Role.RELATIONSHIP_MANAGER)
    _, referenced = _call_with_audio(db, rm, age_days=1)
    _age_file(referenced, 500)                       # old, but a row references it
    young = _orphan()                                # unreferenced but inside the grace period
    queued = _orphan()
    _age_file(queued, 500)
    db.add(MediaDeletion(secure_object_ref=str(queued), reason="t", status=STATUS_PENDING))
    db.commit()
    result = retention.sweep_orphan_files(db)
    assert result["orphans"] == 0 and result["removed"] == 0
    assert referenced.exists() and young.exists() and queued.exists()


def test_dry_run_reports_but_removes_nothing(db, media):
    p = _orphan()
    _age_file(p, 100)
    result = retention.sweep_orphan_files(db, dry_run=True)
    assert result["orphans"] == 1 and result["removed"] == 0 and p.exists()


def test_too_many_orphans_aborts_the_sweep_instead_of_wiping_the_directory(db, media, monkeypatch):
    monkeypatch.setattr(media_storage.settings, "media_orphan_max_per_run", 2)
    files = [_orphan(bytes([i])) for i in range(3)]
    for f in files:
        _age_file(f, 100)
    result = retention.sweep_orphan_files(db)
    db.commit()
    assert result["aborted"] is True and result["removed"] == 0
    assert all(f.exists() for f in files)
    assert len(_audits(db, "media.orphan_sweep_aborted")) == 1


def test_sweep_is_confined_to_the_known_media_subdirectories(db, media):
    stray = media / "somewhere_else" / "keep.txt"
    stray.parent.mkdir(parents=True)
    stray.write_text("not ours")
    _age_file(stray, 1000)
    assert retention.sweep_orphan_files(db)["orphans"] == 0
    assert stray.exists()


# --------------------------------------------------------------------------- commitment + memory lifecycle


def _commit_row(db, *, status, created_days=0, updated_days=0, text="CSP to do X."):
    c = Commitment(
        text=text, party=CommitmentParty.OURS, status=status, source_kind=CommitmentSourceKind.RM_CSP,
    )
    db.add(c)
    db.flush()
    c.created_at = NOW - timedelta(days=created_days)
    c.updated_at = NOW - timedelta(days=updated_days)
    db.commit()
    return c


def test_unreviewed_proposals_expire_but_open_commitments_never_do(db):
    stale = _commit_row(db, status=CommitmentStatus.PROPOSED, created_days=31, updated_days=31)
    fresh = _commit_row(db, status=CommitmentStatus.PROPOSED, created_days=5, updated_days=5)
    open_old = _commit_row(db, status=CommitmentStatus.OPEN, created_days=900, updated_days=900)
    result = commitments_svc.apply_lifecycle(db)
    db.commit()
    db.expire_all()
    assert result["proposals_expired"] == 1
    assert db.get(Commitment, stale.id).status == CommitmentStatus.CANCELLED
    assert db.get(Commitment, fresh.id).status == CommitmentStatus.PROPOSED
    assert db.get(Commitment, open_old.id).status == CommitmentStatus.OPEN      # never auto-expires
    assert len(_audits(db, "commitment.proposal_expired")) == 1


def test_closed_commitments_are_purged_after_the_closed_retention_and_audited_without_text(db):
    old_done = _commit_row(db, status=CommitmentStatus.DONE, created_days=800, updated_days=731, text="SECRET-TEXT-1")
    old_cancelled = _commit_row(db, status=CommitmentStatus.CANCELLED, created_days=800, updated_days=731)
    recent_done = _commit_row(db, status=CommitmentStatus.DONE, created_days=800, updated_days=100)
    result = commitments_svc.apply_lifecycle(db)
    db.commit()
    db.expire_all()
    assert result["closed_purged"] == 2
    assert db.get(Commitment, old_done.id) is None and db.get(Commitment, old_cancelled.id) is None
    assert db.get(Commitment, recent_done.id) is not None
    audits = _audits(db, "commitment.purged")
    assert len(audits) == 2 and all("SECRET-TEXT-1" not in str(a.after) for a in audits)


def test_a_just_expired_proposal_is_not_purged_in_the_same_run(db):
    c = _commit_row(db, status=CommitmentStatus.PROPOSED, created_days=2000, updated_days=2000)
    commitments_svc.apply_lifecycle(db)
    db.commit()
    db.expire_all()
    row = db.get(Commitment, c.id)
    assert row is not None and row.status == CommitmentStatus.CANCELLED   # its closed clock starts now


def test_relationship_memory_only_uses_briefs_inside_the_lookback_window(db, make_user):
    rm = make_user(email="rm-mem@example.com", role=Role.RELATIONSHIP_MANAGER)
    csp = Csp(csp_id="MEM1", name="Mem", rm_name="RM", rm_user_id=rm.id, mobile="9000000007", status=CspStatus.ACTIVE)
    db.add(csp)
    db.commit()
    for days, fact in ((400, "OLD FACT: slab 1 done"), (10, "RECENT FACT: slab 2 pending")):
        call = CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref="9000000007",
                           started_at=NOW - timedelta(days=days), csp_id=csp.id)
        db.add(call)
        db.flush()
        db.add(CallAIAnalysis(call_session_id=call.id, analysis_json={"highlights": [fact]}))
    db.commit()
    facts = [m["fact"] for m in precall.build_for_csp(db, csp)["memory"]]
    assert "RECENT FACT: slab 2 pending" in facts and "OLD FACT: slab 1 done" not in facts


# --------------------------------------------------------------------------- nightly runner


def test_nightly_runs_every_step_and_one_failing_step_does_not_block_the_rest(db, media, make_user, monkeypatch):
    rm = make_user(email="rm-nt@example.com", role=Role.RELATIONSHIP_MANAGER)
    _, audio = _call_with_audio(db, rm, age_days=70)
    orphan = _orphan()
    _age_file(orphan, 100)
    stale = _commit_row(db, status=CommitmentStatus.PROPOSED, created_days=40, updated_days=40)

    summary = retention.run_nightly(db)
    db.expire_all()
    assert summary["rm_audio_purged"] == 1 and summary["orphan_files"]["removed"] == 1
    assert summary["commitments"]["proposals_expired"] == 1
    assert not audio.exists() and not orphan.exists()
    assert db.get(Commitment, stale.id).status == CommitmentStatus.CANCELLED

    # now make the first step blow up: the others must still run and the failure must be visible
    orphan2 = _orphan()
    _age_file(orphan2, 100)

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(retention, "purge_expired_rm_audio", boom)
    summary = retention.run_nightly(db)
    assert summary["rm_audio_purged"] == "failed"
    assert summary["orphan_files"]["removed"] == 1 and not orphan2.exists()


# --------------------------------------------------------------------------- access controls preserved


def test_after_audio_purge_the_owning_rm_still_sees_the_transcript_and_others_still_get_404(
    client, db, media, make_user, login
):
    rm = make_user(email="rm-acc-a@example.com", role=Role.RELATIONSHIP_MANAGER)
    make_user(email="rm-acc-b@example.com", role=Role.RELATIONSHIP_MANAGER)
    make_user(email="dc-acc@example.com", role=Role.DC)
    call, _ = _call_with_audio(db, rm, age_days=75, transcript=True, brief=True)
    retention.purge_expired_rm_audio(db)
    db.commit()

    login("rm-acc-a@example.com", "password123")
    detail = client.get(f"/api/v1/calls/{call.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["transcript_text"] == "hello world" and body["has_voice_note"] is False
    assert client.get(f"/api/v1/calls/{call.id}/voice-note/audio").status_code == 404   # audio is gone

    client.post("/api/v1/auth/logout")
    login("rm-acc-b@example.com", "password123")
    assert client.get(f"/api/v1/calls/{call.id}").status_code == 404                 # another RM: still blocked
    assert client.get(f"/api/v1/calls/{call.id}/voice-note/audio").status_code == 404

    client.post("/api/v1/auth/logout")
    login("dc-acc@example.com", "password123")
    assert client.get(f"/api/v1/calls/{call.id}").status_code == 404                 # a DC: still blocked
