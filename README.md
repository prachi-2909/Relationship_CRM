# Relationship CRM

A standalone relationship system of record — organisation
hierarchy, officials, relationships, interactions, follow-ups, and draft-only
engagement moments.

This repository is **Phase 1** of the build. See `docs/phase-1-spec.html` for the
full scope. No autonomous agent, memory store, or learning layer in this phase.

## Status

**Phase 1 complete** (sub-phases 1A–1E). What's in place:

- **Foundation** — FastAPI on `/api/v1`, SQLAlchemy 2.0, Alembic, session-cookie
  auth, three roles (Admin / Relationship Manager / Approver-Viewer) enforced
  server-side, an `audit_logs` row for every mutation, GitHub Actions CI
- **Organisation & officials** — configurable organisation-unit hierarchy with a tree
  explorer, official profiles with per-field source + verification, timeline
- **Relationships & interactions** — one relationship per official with a
  transparent weighted health score + history + bands; interaction log with
  offline-stub AI extraction (summary / sentiment / commitments / requests /
  people), a pluggable OpenAI-compatible endpoint
- **Follow-ups & ingestion** — tasks (from commitments, with reminders and a
  nightly overdue sweep), CSV/Excel import with dedupe, a worked sample, and an
  admin-only commit
- **Engagement moments** — promotion / birthday / anniversary / inactivity
  detection from verified dates, a "Why now?" evidence panel, communication-
  fatigue suppression, a template draft, and approve / send-by-hand / dismiss.
  **Draft-only — there is no send path.** `ENABLE_MOMENTS=false` is the kill switch.
- Executive dashboard, audit-log viewer, ~66 tests

- **Email ingestion** — paste a raw email or `.eml` body; headers (from / date /
  subject) are parsed, quoted history is collapsed, and the sender is matched to
  an official. Flows into the interaction log via the normal create path.
- **UI** — grouped sidebar, Eko Kiosk branding, IBM Plex Sans Devanagari for
  Hindi, shared components, ~70 backend tests

See `docs/phase-1-spec.html` for scope and `docs/RUNBOOK.md` for operations.
Phase 2 (opportunities, RAG, agent, learning) is not started.

## Layout

```
backend/    FastAPI app, models, migrations, tests
frontend/   React + Vite single-page app
docs/       the Phase 1 specification
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

### Tests

```bash
cd backend
pytest -q
```

Tests run on an in-memory SQLite database by default. Set `TEST_DATABASE_URL` to
run them against Postgres.

## Moving to Postgres later

Models use no SQLite-specific types. When Postgres is introduced (deploy time, or
when the RAG phase needs `pgvector`):

1. `pip install "psycopg[binary]"`
2. Set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/relationship_crm`
3. `alembic upgrade head`
