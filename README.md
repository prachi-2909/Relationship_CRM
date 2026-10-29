# Relationship CRM

A standalone relationship system of record for Eko's SBI work: organisation hierarchy, officials, CSPs (Kiosk Operators), relationships, interactions, follow-ups, call intelligence, and draft-only engagement moments. It has a web CRM and an Android app for District Coordinators.

This repository started as **Phase 1** (see `docs/phase-1-spec.html`) and now also carries the autonomous agent, memory and learning layers, and the mobile call-intelligence module. See "Beyond Phase 1" and "Call intelligence" below.

## Status

**Phase 1 complete** (sub-phases 1A-1E). What's in place:

- **Foundation**: FastAPI on `/api/v1`, SQLAlchemy 2.0, Alembic, session-cookie auth, three roles (Admin / Relationship Manager / Approver-Viewer) enforced server-side, an `audit_logs` row for every mutation, GitHub Actions CI
- **Organisation & officials**: configurable organisation-unit hierarchy with a tree explorer, official profiles with per-field source + verification, timeline
- **Relationships & interactions**: one relationship per official with a transparent weighted health score + history + bands; interaction log with offline-stub AI extraction (summary / sentiment / commitments / requests / people), a pluggable OpenAI-compatible endpoint
- **Follow-ups & ingestion**: tasks (from commitments, with reminders and a nightly overdue sweep), CSV/Excel import with dedupe, a worked sample, and an admin-only commit
- **Engagement moments**: promotion / birthday / anniversary / inactivity detection from verified dates, a "Why now?" evidence panel, communication-fatigue suppression, a template draft, and approve / send-by-hand / dismiss. **Draft-only, there is no send path.** `ENABLE_MOMENTS=false` is the kill switch.
- **Executive dashboard**, audit-log viewer
- **Email ingestion**: paste a raw email or `.eml` body; headers are parsed, quoted history is collapsed, and the sender is matched to an official. Flows into the interaction log via the normal create path.
- **Relationship Brief**: `GET /relationships/{id}/brief`, a read-only synthesis of one relationship. Prose via the configured LLM, deterministic template otherwise. No writes.
- **Stakeholder graph**: typed edges between officials (`reports_to` / `works_with` / `introduced_by`), asserted manually or suggested from officials co-mentioned in one interaction, then confirmed or dismissed by a human.
- **UI**: grouped sidebar, Eko Kiosk branding, IBM Plex Sans Devanagari for Hindi, shared components

See `docs/phase-1-spec.html` for scope and `docs/RUNBOOK.md` for operations.

## Beyond Phase 1

Opportunity management, the Level 0-1 autonomous agent (observe + recommend only), and the RAG/memory/learning layer are implemented on top of the Phase 1 foundation:

- **RAG**: `/ask` and the Relationship Brief narrative are grounded in retrieved passages from interaction notes, sent moment drafts, and opportunity details, each with a source, snippet, similarity score and confidence tier. Semantic search runs on a deterministic offline embedding stub by default, or any OpenAI-compatible `/embeddings` endpoint (`EMBEDDING_BASE_URL`). `ENABLE_RAG=false` is the kill switch.
- **Semantic memory**: durable facts about an official (`GET/POST /officials/{id}/facts`), with conflict-aware writes: a human-confirmed fact never loses to a lower-confidence auto-extraction.
- **Strategic memory**: evidence-backed insights computed from real historical data only, never an LLM guess, and never created below a minimum sample size.
- **Outcome tracking & evaluation**: every approved agent recommendation gets a deterministic outcome verdict once its task/moment/opportunity resolves, reconciled nightly.
- **Strategy registry & controlled experiments**: versioned strategies assigned via controlled experiments and promoted only by an explicit admin action gated on a minimum sample size.
- **Learning Dashboard** (`/learning`, admin-only): strategies, experiments, outcomes, evaluation metrics and human corrections in one place.

The agent remains **Level 0-1 throughout**: nothing writes a real domain object without the existing human-approval gate, and no strategy is ever promoted automatically.

## Call intelligence

Two call streams are handled separately:

| | DC <-> SBI official | RM <-> CSP (Kiosk Operator) |
|---|---|---|
| Recorded by | the Android app (DC) | the Android app (RM), CSP numbers only |
| Audio | deleted once the call is logged as an Interaction | deleted 60 days after it was stored |
| Transcript, AI brief, summary | **kept** | **kept** |

- Calls shorter than 5 seconds are not recorded (the app discards the audio and the server refuses it).
- Audio is transcribed on the server by a self-hosted Whisper service (`transcription` in `docker-compose.yml`, OpenAI-compatible). Call audio does not leave the host.
- **Commitments**: extracted from calls, duplicate-checked against open commitments, reviewed by a human before they count; an unreviewed proposal expires after 30 days.
- **Pre-call briefing**: before calling a CSP or an SBI official, the app and web CRM show relationship memory, open commitments, suggestions with outcome feedback, and a performance review.
- **Supervisor (`/ask`)**: answers questions about officials and CSPs from the recorded call history. An RM sees only their own CSPs. Without an LLM it answers from a deterministic template.
- **Data protection (DPDP)**: `AI_DATA_PROCESSING_ENABLED` is the master switch for sending anything to an AI endpoint. Retention periods, deletion and audit events are in `docs/data-retention.md` and are configurable in `backend/app/config.py`; they are defaults, not yet confirmed by compliance.

## Android app

`android/` holds the DC / RM app (Kotlin, Jetpack Compose, `minSdk 26`). It logs in to the same API, detects calls, records them (two-way recording via Shizuku, based on CallVault), uploads the audio for transcription, and shows pre-call briefings and commitments. The API base URL is a build property:

```bash
cd android
gradle :app:assembleDebug -PrcrmApiBaseUrl=https://<your-domain>/sbi-relationship-crm/api/v1/
```

The APK is at `android/app/build/outputs/apk/debug/app-debug.apk`. Without the property, a debug build points at a LAN address for same-Wi-Fi testing.

## Layout

```
backend/    FastAPI app, models, migrations, tests
frontend/   React + Vite single-page app
android/    Android app (Kotlin / Compose)
docs/       Phase 1 specification, RUNBOOK, data-retention policy
```

## Running it

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
alembic upgrade head
python -m app.scripts.create_admin --email you@eko.co.in --name "Your Name" --password "change-me"
python -m uvicorn app.main:app --reload --port 8010
```

API docs at http://localhost:8010/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App at http://localhost:5173 (proxies `/api` to the backend on :8010).

### With Docker

```bash
copy .env.example .env      # then set CRM_HOST_PORT=8080 and PUBLIC_BASE_PATH=/ for a local run
docker compose up --build
docker compose exec backend python -m app.scripts.create_admin \
    --email you@eko.co.in --name "Your Name" --password "change-me"
```

App at http://127.0.0.1:8080 (nginx serves the built frontend and proxies `/api` to the backend container). Only the frontend is published, and only on `127.0.0.1:CRM_HOST_PORT`; the backend and the transcription service have no host port. Data persists in the `crm-data` volume (the Whisper model cache in `hf-cache`). `LLM_*` in `.env` is optional; without it the app uses its offline stub.

### Shared server (behind Nginx, under a sub-path)

The same compose file runs on a shared server: bind the frontend to a free localhost port (`CRM_HOST_PORT`), set `PUBLIC_BASE_PATH=/sbi-relationship-crm/`, and add one Nginx `location` that proxies that path to the port. See "Shared server" in `docs/RUNBOOK.md` for the drop-in, first admin, data loading, updating and rollback.

### Tests

```bash
cd backend
pytest -q
```

Tests run on an in-memory SQLite database by default. Set `TEST_DATABASE_URL` to run them against Postgres.

## Database

SQLite in WAL mode (30 s busy timeout), on a local disk or Docker volume. Backups use SQLite's backup API; a plain file copy of a running database can miss the newest writes (see `docs/RUNBOOK.md`, "SQLite under load").

### Moving to Postgres later

Models use no SQLite-specific types. When the load calls for it:

1. `pip install "psycopg[binary]"`
2. Set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/relationship_crm`
3. `alembic upgrade head`

## License

This project is licensed under the GNU General Public License v3.0 - see [LICENSE](LICENSE). The Android call recorder is based on CallVault, which is GPL-3.0, so the app and the code that ships with it stay under the same licence.

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.
