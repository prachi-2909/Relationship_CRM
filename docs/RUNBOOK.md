# Operations runbook

Phase 1 — Relationship CRM. SQLite, single service, no external
dependencies. Everything below assumes `backend/` as the working directory
unless noted.

## First run

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
alembic upgrade head
python -m app.scripts.create_admin --email you@eko.co.in --name "You" --password "..."
python -m app.scripts.seed_demo          # optional: illustrative demo data
python -m uvicorn app.main:app --reload --port 8010
```

Frontend: `cd ../frontend && npm install && npm run dev` (proxies `/api` to :8010).

## Database

- Location: `backend/relationship_crm.db` (git-ignored). It is the whole database.
- **Backup:** copy the file while the server is stopped, or use
  `sqlite3 relationship_crm.db ".backup backup.db"` while it is running.
- **Restore:** stop the server, replace the file, start again.
- **Reset:** stop the server, `rm relationship_crm.db`, `alembic upgrade head`,
  re-create the admin, optionally re-seed.
- **Schema change:** `alembic revision -m "..."` then `alembic upgrade head`.
  Never edit a migration that has run anywhere else.

## Migrations

```bash
alembic upgrade head        # apply
alembic downgrade -1        # roll back one
alembic history             # list
```

## Background jobs

APScheduler runs one nightly job at 03:00 UTC: recompute every relationship
score, escalate overdue tasks, detect engagement moments.

- Disable entirely: `ENABLE_SCHEDULER=false` in `.env` (restart).
- Run the overdue sweep now: `POST /api/v1/tasks/run-overdue-sweep` (admin).
- Run moment detection now: `POST /api/v1/moments/detect` (admin).

## Engagement moments — the kill switch

`ENABLE_MOMENTS=false` in `.env` (restart) stops **all** detection and drafting.
Existing moments stay visible; no new ones are created and `/moments/detect`
and `/moments/{id}/draft` return 409.

There is no send path anywhere in the system. A moment never advances past
`draft_ready` on its own. `approved` / `sent_manually` / `dismissed` are all
explicit human actions, and "sent" only records that a person sent it by hand.

## Tuning (all in `.env`, restart to apply)

| Variable | Default | Effect |
|---|---|---|
| `SESSION_TTL_HOURS` | 8 | login session lifetime |
| `LLM_BASE_URL` / `LLM_MODEL` | (unset) → offline stub | interaction extraction endpoint |
| `MOMENT_LOOKAHEAD_DAYS` | 7 | how far ahead birthdays / anniversaries are surfaced |
| `MOMENT_INACTIVITY_DAYS` | 35 | silence before an inactivity moment |
| `MOMENT_FATIGUE_DAYS` | 21 | recent-contact window that suppresses a moment |
| `MOMENT_PROMOTION_RECENT_DAYS` | 30 | how recent a promotion date must be |
| `OVERDUE_ESCALATION_DAYS` | 3 | (reserved for a future escalation tier) |

## Tests

```bash
pytest -q                                  # ~66 tests, in-memory SQLite
TEST_DATABASE_URL=postgresql+psycopg://... pytest -q   # against Postgres
```

## Moving to PostgreSQL

Models use no SQLite-specific types.

```bash
pip install "psycopg[binary]"
# .env
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/relationship_crm
alembic upgrade head
```

## Health

`GET /api/v1/health` → `{status, time, database}`. `status` is `degraded` if the
database is unreachable.
