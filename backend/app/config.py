"""Application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Relationship CRM"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite+pysqlite:///./relationship_crm.db"

    session_cookie_name: str = "rcrm_session"
    session_ttl_hours: int = 8
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    # Narrow this to the public sub-path (e.g. /sbi-relationship-crm/) when the app shares a domain with others.
    session_cookie_path: str = "/"

    cors_origins: list[str] = ["http://localhost:5173"]

    secret_key: str = "dev-insecure-change-me"

    # A stable INBOUND API key for connecting another agent / service to this CRM
    # later, without a human login that expires. Stored in .env (never committed).
    # NOTE: no endpoint consumes this yet - it is a reserved slot only. Wiring it to
    # an X-API-Key auth path (scoped access, rate-limit, audit) is a deliberate
    # future step, because a static key grants programmatic access to the API.
    crm_api_key: str | None = None

    # AI extraction. With no base URL, a deterministic offline stub is used so the
    # pipeline stays testable; set these to point at any OpenAI-compatible endpoint
    # (Ollama, vLLM, NVIDIA NIM, a hosted gateway).
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "stub"
    llm_timeout_seconds: float = 30.0

    # DPDP master switch. When False, NO audio or text is sent to ANY AI endpoint - transcription,
    # LLM and embeddings all fall back to their offline stubs, regardless of the *_base_url values.
    # Lets a deployment guarantee nothing leaves the server even if endpoints are still configured.
    # For DPDP compliance those endpoints should themselves be self-hosted inside India; see
    # deploy/self-hosted-ai/README.md.
    ai_data_processing_enabled: bool = True

    # Android hardware Key Attestation (sideloaded / non-Google-Play fleets). When True, the backend
    # BLOCKS requests from devices that fail attestation; keep False (report-only, audit a verdict
    # but never block) until the verifier is validated on real devices and Google roots are pinned in
    # app/security/google_attestation_roots.pem. See app/security/key_attestation.py.
    require_device_attestation: bool = False

    # Background jobs: nightly score recompute + overdue-task sweep.
    enable_scheduler: bool = True
    overdue_escalation_days: int = 3

    # Engagement moments. enable_moments is the kill switch — turning it off
    # stops all detection and drafting without a deploy.
    enable_moments: bool = True
    moment_lookahead_days: int = 7
    moment_inactivity_days: int = 35
    moment_fatigue_days: int = 21
    moment_promotion_recent_days: int = 30

    # Autonomous agent (observe + recommend only — it never writes a real
    # domain object itself; a human must approve every recommendation).
    # enable_agent is the kill switch, same pattern as enable_moments.
    enable_agent: bool = True
    agent_portfolio_scan_limit: int = 20
    agent_max_relationships_per_run: int = 10
    agent_recommendation_ttl_days: int = 14
    # episodic memory: how long an explicit human rejection of a
    # recommendation type is respected before the agent may propose that
    # type again for the same relationship.
    agent_rejection_cooldown_days: int = 14

    # Automated backups. enable_backups is the kill switch. backup_dir is
    # relative to the database file's own directory (so it lands inside the
    # same Docker volume with zero extra config); backup_retention_count
    # caps how many nightly snapshots are kept.
    enable_backups: bool = True
    backup_dir: str = "backups"
    backup_retention_count: int = 7

    # RAG (retrieval-augmented /ask and Brief narratives). enable_rag is the
    # kill switch. embedding_base_url falls back to llm_base_url when unset,
    # so a single configured endpoint covers both chat and embeddings unless
    # they genuinely differ.
    enable_rag: bool = True
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "stub"
    embedding_dim: int = 256
    rag_top_k: int = 5
    rag_max_chars_budget: int = 4000
    rag_min_similarity: float = 0.15

    # Semantic memory: durable facts about an official, extracted from
    # interaction text. Strategic memory: evidence-backed insights computed
    # from real outcome data (never an LLM guess). Both kill-switched
    # independently of the agent/RAG switches above.
    enable_semantic_memory: bool = True
    enable_strategic_insights: bool = True
    strategic_insight_min_sample: int = 5

    # Mobile Call Intelligence. enable_call_intelligence is the kill switch.
    # Knowlarity/transcription are unset by default -> every call to them is a
    # graceful no-op/stub, same offline-first pattern as llm_base_url.
    #
    # telephony_provider selects who places an outgoing call: "knowlarity" (default -
    # the backend triggers Knowlarity's Click-to-Call API, unchanged) or
    # "android_native" (the backend does nothing here - the DC's own app dials via the
    # device's SIM and reports the outcome back via /calls/{id}/native/complete).
    enable_call_intelligence: bool = True
    telephony_provider: str = "knowlarity"
    knowlarity_base_url: str | None = None
    knowlarity_api_key: str | None = None
    knowlarity_number: str | None = None
    knowlarity_webhook_secret: str | None = None
    # "local_whisper" = open-source faster-whisper running IN this process (no Groq, nothing leaves the
    # server). "openai" = an OpenAI-compatible HTTP endpoint (Groq/self-hosted). Transcription always
    # runs in the BACKGROUND so an upload never waits for it.
    transcription_provider: str = "local_whisper"
    local_whisper_model: str = "medium"  # base < small < medium < large-v3 (accuracy up, speed down).
    # "medium" reliably catches figures/targets/deadlines in Hindi-English calls where "small" drops
    # them; on CPU it runs ~1.2x real-time (fine in the background). Drop to "small" for low-RAM boxes.
    local_whisper_compute: str = "int8"  # int8 = fast on CPU; float16 on GPU
    # Gently denoise call audio (speech-safe, via PyAV) before transcription to lift quality on
    # noisy/quiet recordings. Never removes speech; falls back to the raw audio if it fails.
    transcription_denoise_enabled: bool = True
    transcription_base_url: str | None = None
    transcription_api_key: str | None = None
    # Seconds to wait for a remote transcription. CPU Whisper runs about real-time, so long calls need minutes.
    transcription_timeout_seconds: float = 60.0
    transcription_model: str = "whisper-large-v3-turbo"
    # Hinglish: DC calls are Hindi/English code-mixed. Setting the language to Hindi captures that
    # far better than auto-detect, and seeding a romanized (Hinglish) prompt biases Whisper to write
    # Hindi in the Latin script the staff read, rather than Devanagari. Both are tunable per deployment.
    transcription_language: str | None = "hi"
    # A SHORT seed only. Whisper's prompt is a context hint, not an instruction - a long/forcing
    # prompt makes it hallucinate or repeat the prompt. A brief Hinglish seed nudges Roman-script
    # output while keeping accuracy. Blank it (TRANSCRIPTION_PROMPT=) if transcripts look wrong.
    transcription_prompt: str | None = "Haan ji, namaste. Banking call."
    # Call audio exists only to be transcribed, never to be stored (DPDP Act data
    # minimisation): it is always deleted the moment the call is logged into the CRM -
    # that is not configurable. A call that is never logged keeps its audio at most this
    # many days, after which the nightly job deletes it anyway.
    unconfirmed_call_audio_retention_days: int = 7
    # An in-app call whose session was created but never reported back (the dialer never opened, the app was
    # killed, a permission popup was lost) is cancelled after this long, so it does not sit in Pending forever.
    abandoned_native_call_hours: int = 3
    # RM <-> CSP call RECORDINGS (the audio only) are deleted this many days after they were stored.
    # Transcripts and AI briefs are NOT touched by this - see docs/data-retention.md.
    rm_recording_retention_days: int = 60
    # A call shorter than this (a dropped, mis-dialled or instantly hung-up call) is not worth keeping or
    # transcribing: its recording is refused and the app discards it.
    min_recording_seconds: int = 5
    # Failed file deletions are queued and retried with backoff; after this many failed attempts the
    # deletion is marked "abandoned" and audited so an operator can step in.
    media_delete_max_attempts: int = 8
    # Orphan-file sweep: a file under the media dir that no database row references is removed, but only
    # once it is older than this (so an upload still being committed is never mistaken for an orphan),
    # and never more than this many in one run (a safety stop against a misconfigured DB pointing at an
    # emptier database wiping the media directory).
    media_orphan_grace_hours: int = 24
    media_orphan_max_per_run: int = 50
    # Commitment lifecycle (separate from audio): an AI proposal nobody reviewed expires after N days;
    # a closed (done/cancelled/expired) commitment is deleted N days after it was closed. OPEN
    # commitments never expire - an open promise stays visible until a human closes it.
    commitment_proposal_expiry_days: int = 30
    commitment_closed_retention_days: int = 730
    # Relationship memory for a CSP is derived from its call briefs; only briefs from the last N days
    # feed it, so stale facts age out of pre-call intelligence.
    memory_lookback_days: int = 365
    # Intelligence feedback rows (useful / relevant verdicts) snapshot the suggestion text, which comes
    # from call briefs, so they are deleted this many days after the verdict was last changed. The
    # aggregate quality numbers are computed on demand from what remains.
    intelligence_feedback_retention_days: int = 730
    call_pending_reminder_hours: int = 4
    # Daily CSP sync from the live "Calling Sheet" Google Sheet (public CSV export). Keeps each
    # CSP's name, number, alternate number and assigned RM current, and deactivates CSPs that are
    # no longer active there. Runs every evening (see csp_sync_hour) when csp_sync_enabled.
    csp_sync_enabled: bool = True
    csp_sync_hour: int = 20  # 8 PM India time (the job's trigger uses Asia/Kolkata explicitly)
    csp_sync_timezone: str = "Asia/Kolkata"
    csp_sheet_id: str = "1KHy7ejiUWZg9EQA0x4lm0axnVS5Hpiw1vLruc-0jSOg"
    csp_sheet_gid: str = "1807123739"
    # Email is sent through Eko's Gmail Template Sender (MCP over HTTP) - branded HTML template +
    # Gmail delivery from an already-authorised account, so no SMTP credentials are needed here,
    # only the shared API key. Set gmail_mcp_api_key via env / .env; nothing is sent without it.
    gmail_mcp_url: str = "https://indev.eko.in/gmail/mcp"
    gmail_mcp_api_key: str | None = None
    smtp_from_name: str = "Eko Relationship Team"
    # TESTING SAFETY: while True, NO real email is ever sent - birthday wishes are only drafted
    # (recipient + subject + body returned/logged for review). Flip to False to actually send.
    email_draft_only: bool = True
    # Daily CSP birthday wishes: emails active CSPs whose birthday is today. Runs every morning
    # when enabled (and SMTP is configured).
    csp_birthday_wishes_enabled: bool = False  # OFF for now - no mail activity until re-enabled
    csp_birthday_hour: int = 9  # 9 AM India time
    csp_birthday_subject: str = "Happy Birthday from your SBI team!"
    # Local disk storage for uploaded DC voice notes, relative to the
    # database file's own directory (same convention as backup_dir). Swap
    # for real object storage later purely via config - the rest of the
    # pipeline only ever deals in a secure_object_ref string.
    media_dir: str = "media"

    # Android app self-update: the DC app checks GET /app/version on launch
    # and, if newer, downloads GET /app/download and prompts a single tap to
    # install (Android has no silent-install path for a sideloaded app
    # without enterprise/MDM management - this is the closest to "automatic"
    # that's actually possible). Bumped by app/scripts/publish_android_release.py.
    android_release_dir: str = "releases"
    android_latest_version_code: int = 1
    android_latest_version_name: str = "1.0"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
