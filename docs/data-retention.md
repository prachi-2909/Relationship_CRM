# Data retention

What is kept, for how long, who deletes it, and how deletion is proved. Every period below is a
setting in `backend/app/config.py` (env var = the field name upper-cased) unless it says "fixed".

## The two call streams are governed separately

| | DC <-> SBI official | RM <-> CSP (Kiosk Operator) |
|---|---|---|
| **Audio** | Deleted when the call is logged into the CRM (the Interaction). Never logged: deleted after `unconfirmed_call_audio_retention_days` (7). | Deleted `rm_recording_retention_days` (**60**) days after it was stored. Audio only. |
| **Transcript** | Goes with the audio at logging (its text survives in the CRM Interaction's notes). | **Retained. Explicitly excluded from the audio purge.** |
| **AI brief** | Goes with the audio at logging (survives in the Interaction's summary/structured fields). | **Retained**, same as the transcript. |
| **Who can see it** | The DC who made the call, plus staff roles. | The RM who made the call, plus admin/viewer roles. An RM sees only their own CSPs. |
| **Code** | `services/call_intelligence.py` (`confirm_and_log`, `purge_stale_call_audio`) - unchanged. | `services/retention.py` (`purge_expired_rm_audio`). |

The 60 days count from when the audio was stored (`created_at` of the stored recording), not from the
call time. A purged call keeps its transcript, brief and commitments; the API reports
`has_voice_note: false` and the audio endpoint returns 404, and both the web CRM and the Android app
already hide playback in that case.

## Commitments and relationship memory (separate from audio)

| Data | Rule | Setting |
|---|---|---|
| Commitment **proposed** by the AI, not reviewed | Expires to *cancelled* after N days (audited `commitment.proposal_expired`). | `commitment_proposal_expiry_days` = 30 |
| Commitment **open** | Never expires. It stays until a human marks it done or cancelled. | - |
| Commitment **done / cancelled / expired** | Deleted N days after it was closed (audited `commitment.purged`, ids and status only - never the text). | `commitment_closed_retention_days` = 730 |
| CSP **relationship memory** | Derived, not stored: built from briefs on demand. Only briefs from the last N days contribute, so old facts age out of pre-call intelligence. | `memory_lookback_days` = 365 |
| Commitment **history** (`commitment_events`) | Ids and scalars only (status, outcome, who acted, duplicate links) - never text. Deleted with its commitment. | follows `commitment_closed_retention_days` |
| **Outcome feedback** (`intelligence_feedback`) | One row per user per suggestion: verdict, the suggestion's text snapshot, and who gave it. Deleted N days after the verdict was last changed (audited `intelligence.feedback_purged`, counts only). | `intelligence_feedback_retention_days` = 730 |

These are defaults chosen to be conservative and are **not yet confirmed by compliance** - change them
in config, no code change needed. The same rules apply to both call streams; `source_kind` on each
commitment (`rm_csp` / `dc_official`) lets a per-stream rule be added later.

## What is not covered yet

* **Transcripts and AI briefs of RM calls have no automated deletion.** That is the stated policy for now
  (they are excluded from the 60-day purge), but it means they are kept indefinitely. A transcript
  retention period is a decision still to be made.
* Provider-hosted recordings (a URL, not a file we stored) are never deleted by us.

## How deletion is made trustworthy

* **Outbox** (`media_deletions` table). The intent to delete a file is written in the same transaction
  that removes the database row, and the file is removed after the commit. A rollback discards the
  intent, so the file survives; a crash after commit leaves a pending row.
* **Retries.** A failed delete (for example a locked file) is retried with backoff (5 min, 10, 20 ... up
  to a day). After `media_delete_max_attempts` (8) failures it is marked `abandoned` and audited so an
  operator can step in. A path outside the media directory, or a URL, is refused and never deleted.
* **Orphan sweep.** A file under `media/voice_notes` that no row references and that is older than
  `media_orphan_grace_hours` (24) is removed. If more than `media_orphan_max_per_run` (50) turn up in
  one run, the sweep does nothing and audits `media.orphan_sweep_aborted`: that pattern means the
  database and the media directory disagree and a person must look.
* **Schedule.** `retention.run_nightly` runs inside the nightly job. Each step commits or rolls back on
  its own, so one failure never blocks the others.

## Audit events

`call.audio_purged_retention_expired` (RM audio; records scope, age, whether a transcript existed),
`media.delete_failed`, `media.delete_retried_ok`, `media.delete_abandoned`, `media.orphan_removed`,
`media.orphan_remove_failed`, `media.orphan_sweep_aborted`, `commitment.proposal_expired`,
`commitment.purged`, `intelligence.feedback` (a verdict given), `intelligence.feedback_purged`, plus the existing `call.artifacts_discarded_after_logging` and
`call.artifacts_discarded_retention_expired` for the DC stream. Audit entries carry file names, never
full paths, and never transcript or commitment text.
