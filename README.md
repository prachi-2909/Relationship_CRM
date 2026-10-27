# Relationship CRM

A standalone relationship system of record — organisation
hierarchy, officials, relationships, interactions, follow-ups, and draft-only
engagement moments.

This repository is **Phase 1** of the build. See `docs/phase-1-spec.html` for the
full scope. It now also carries the autonomous agent, memory, and learning layers
that were originally scoped as later phases — see "Beyond Phase 1" below.

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
- Executive dashboard, audit-log viewer

- **Email ingestion** — paste a raw email or `.eml` body; headers (from / date /
  subject) are parsed, quoted history is collapsed, and the sender is matched to
  an official. Flows into the interaction log via the normal create path.
- **Relationship Brief** — `GET /relationships/{id}/brief`, a read-only synthesis
  of one relationship (what matters, what changed, whether to reconnect, the next
  interaction, the stakeholders). Prose via the configured LLM, deterministic
  template otherwise. No writes.
- **Stakeholder graph** — typed edges between officials (`reports_to` /
  `works_with` / `introduced_by`). Asserted manually or *suggested* from
  officials co-mentioned in one interaction, then confirmed or dismissed by a
  human. Surfaced read-only in the Brief.
- **UI** — grouped sidebar, Eko Kiosk branding, IBM Plex Sans Devanagari for
  Hindi, shared components, ~86 backend tests

See `docs/phase-1-spec.html` for scope and `docs/RUNBOOK.md` for operations.

## Beyond Phase 1

Opportunity management, the Level 0–1 autonomous agent (observe + recommend
only — see "Autonomous agent" below), and the RAG/memory/learning layer are
now implemented on top of the Phase 1 foundation:

- **RAG** — `/ask` and the Relationship Brief narrative are grounded in
  retrieved passages from interaction notes, sent moment drafts, and
  opportunity details (`GET /ask` → `sources`, each with a source row,
  a snippet, a similarity score, and a confidence tier), not the entire
  database dumped into the prompt. Semantic search runs on a
  deterministic offline embedding stub by default, or any OpenAI-compatible
  `/embeddings` endpoint (`EMBEDDING_BASE_URL`). `ENABLE_RAG=false` is the
  kill switch.
- **Semantic memory** — durable, open-ended facts about an official
  (`GET/POST /officials/{id}/facts`), with conflict-aware writes: a
  human-confirmed fact never loses to a lower-confidence auto-extraction.
  Never hallucinated offline — the deterministic stub extracts nothing
  rather than guessing.
- **Strategic memory** — evidence-backed insights computed from real
  historical data only (task completion rate, moment response rate,
  recommendation approval rate), never an LLM guess, and never created
  below a minimum sample size (`GET /officials/{id}/insights`).
- **Outcome tracking & evaluation** — every approved agent recommendation
  gets a deterministic outcome verdict once its task/moment/opportunity
  resolves (`GET /agent/recommendations/{id}/outcome`,
  `GET /agent/evaluation`), reconciled nightly.
- **Strategy registry & controlled experiments** — named strategies with
  versioned config, assigned to relationships via a controlled
  experiment, evaluated, and promoted only by an explicit admin action
  gated on a minimum sample size (`/strategies/*`, admin-only). An
  unassigned relationship's agent behavior is unaffected.
- **Learning Dashboard** (`/learning`, admin-only) — strategy registry,
  experiments, outcomes, evaluation metrics, and human corrections
  (rejected recommendations) in one place. The Autonomous Agent page's
  recommendation detail also shows retrieved knowledge, semantic/strategic
  memory, and the outcome once resolved, alongside the existing evidence.

The agent remains **Level 0–1 throughout**: nothing above writes a real
domain object without the existing human-approval gate, and no strategy is
ever promoted automatically.

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

### With Docker

```bash
copy .env.example .env      # optional: set SECRET_KEY / LLM_* for this stack
docker compose up --build
docker compose exec backend python -m app.scripts.create_admin \
    --email you@eko.co.in --name "Your Name" --password "change-me"
```

App at http://localhost (nginx serves the built frontend and proxies `/api` to
the backend container). The backend's own port is also published at
`:8010` (API docs at http://localhost:8010/docs). Data persists in the
`crm-data` named volume between restarts — see `docs/RUNBOOK.md` for backup/
restore with Docker.

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

## License

This project is licensed under the GNU General Public License v3.0 - see [LICENSE](LICENSE). The Android call recorder is
based on CallVault, which is GPL-3.0, so the app and the code that ships with it stay under the same licence.

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.
