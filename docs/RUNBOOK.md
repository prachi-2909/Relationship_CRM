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
- **Automated backup:** the nightly job (03:00 UTC) snapshots the database into
  `backend/backups/` via SQLite's own online backup API, keeping the last
  `BACKUP_RETENTION_COUNT` (default 7). `ENABLE_BACKUPS=false` is the kill
  switch. `GET /api/v1/health` reports `last_backup_at` so this is
  monitorable without a separate dashboard.
- **Manual backup:** copy the file while the server is stopped, or use
  `sqlite3 relationship_crm.db ".backup backup.db"` while it is running.
- **Restore:** stop the server, replace the file (from `backend/backups/` or
  a manual copy), start again.
- **Reset:** stop the server, `rm relationship_crm.db`, `alembic upgrade head`,
  re-create the admin, optionally re-seed.
- **Schema change:** `alembic revision -m "..."` then `alembic upgrade head`.
  Never edit a migration that has run anywhere else.

## Docker

`docker compose up --build` runs the whole stack: `backend` (runs
`alembic upgrade head` on every start, then serves on :8010) and `frontend`
(nginx, :80, proxies `/api` to `backend:8010`). The database lives on the
`crm-data` named volume, not a bind mount.

- **First run:** `docker compose exec backend python -m app.scripts.create_admin
  --email you@eko.co.in --name "You" --password "..."`.
- **Backup:** the nightly automated backup already lands at
  `/app/data/backups/` inside the `crm-data` volume (same mechanism as local
  dev — see "Database" above). To pull the latest one to the host:
  `docker cp $(docker compose ps -q backend):/app/data/backups/<file> .`
  (list files first with `docker compose exec backend ls /app/data/backups`).
  For an on-demand snapshot: `docker compose exec backend sqlite3
  /app/data/relationship_crm.db ".backup /app/data/backup.db"`, then `docker cp
  $(docker compose ps -q backend):/app/data/backup.db .`.
- **Restore:** stop the stack, `docker volume rm <project>_crm-data` (destructive
  — only after confirming a good backup exists), copy the backup file onto a
  fresh volume (e.g. via a throwaway container mounting the same volume), then
  `docker compose up -d` again.
- **Logs:** `docker compose logs -f backend` / `frontend` — stdout is one-line
  JSON per entry; pipe through `jq` for readability.
- **Health:** both images define a `HEALTHCHECK` hitting `/api/v1/health` (backend)
  and `/` (frontend) — `docker compose ps` shows current status.
- **Config:** copy `.env.example` (repo root) to `.env` to set `SECRET_KEY`
  and `LLM_*` for the compose stack — separate from `backend/.env`, which only
  applies to a local non-Docker `uvicorn` run.
- **TLS:** this stack ships no TLS termination — `nginx.conf` only listens on
  `:80`. The session cookie defaults to `Secure`, so login will not persist
  over plain HTTP on anything other than `http://localhost` (browsers exempt
  that host specifically). Deploying anywhere reachable by others means
  putting a TLS-terminating reverse proxy in front; don't set
  `SESSION_COOKIE_SECURE=false` to work around this unless the deployment is
  genuinely isolated with no TLS by design.
- Same migration/schema-change discipline as above — migrations run
  automatically on container start, so ship the migration file with the image.

## Shared server, behind Nginx under a sub-path

This is how the stack is deployed on the shared R730: the public link is
`https://indev.eko.in/sbi-relationship-crm/` (no IP, no application port). Public traffic enters the host
Nginx on 80/443, which routes the sub-path to the frontend container on `127.0.0.1:<CRM_HOST_PORT>`. Nothing
else is published (the backend has no host port; the frontend proxies `/api` to it over the compose network).

1. **Pick a free port (read-only).** `sudo ss -lntp` and `docker ps`; choose one that is unused, never an
   infrastructure port. Do not touch other apps.
2. **`.env`** at the repo root (`cp .env.example .env`, `chmod 600 .env`):
   `CRM_HOST_PORT=<free port>`, `PUBLIC_BASE_PATH=/sbi-relationship-crm/` (must start and end with `/`),
   and the usual `SECRET_KEY`, `LLM_*`. The session cookie is scoped to `PUBLIC_BASE_PATH` and stays `Secure`.
3. **Start:** `sudo docker compose up -d --build` (the compose project is named `sbi-relationship-crm`; never
   run `docker system prune` or `down` on another project). Check `curl -i http://127.0.0.1:<port>/` and
   `curl -i http://127.0.0.1:<port>/api/v1/health`.
4. **Nginx (needs the server admin's approval).** The `indev.eko.in` block already includes
   `/etc/nginx/eko-platform/routes.conf`, which includes `routes.d/*.conf`, so each app adds **one file of its
   own** there and no existing file is edited. Create `/etc/nginx/eko-platform/routes.d/sbi-relationship-crm.conf`
   (refuse if it already exists), then `sudo nginx -t` and only if it passes `sudo systemctl reload nginx`
   (if the test fails, delete just that file):

   ```nginx
   location = /sbi-relationship-crm { return 301 /sbi-relationship-crm/; }
   location ^~ /sbi-relationship-crm/ {
       proxy_pass http://127.0.0.1:<CRM_HOST_PORT>/;   # the trailing slash strips the prefix
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_read_timeout 300s;
   }
   ```
   The server block already sets `client_max_body_size 100m`, which covers call-audio uploads (the API caps a
   file at 20 MB), so none is set here. `^~` stops regex locations from taking the path.
5. **Verify the exact link** `https://indev.eko.in/sbi-relationship-crm/`: login page loads, assets 200, login
   persists, and a call recording uploads. Then confirm the other apps on the server are still healthy.
   A quick check from the server: `curl -skI --resolve indev.eko.in:443:127.0.0.1 https://indev.eko.in/sbi-relationship-crm/`.
6. **First admin, or load existing data.** A new deployment starts with an empty database:
   `docker compose exec backend python -m app.scripts.create_admin --email ... --name ... --password ...`
   (type the password yourself; do not paste it into chat or leave it in shell history). To seed it from a
   cleaned copy of another database instead: take a backup first
   (`docker compose cp backend:/app/data/relationship_crm.db <backup>`), `docker compose stop backend`, remove
   the stale `-wal`/`-shm` files in the volume, `docker compose cp <clean.db> backend:/app/data/relationship_crm.db`,
   `docker compose start backend`. The copy must be at the same migration head, must have no live sessions
   (`delete from sessions`), and carries personal data and password hashes: delete every copy afterwards and
   reset the passwords.
7. **Updating.** `git pull` as the repository's owner (`sudo -u <owner> git -C <dir> pull`; root hits git's
   "dubious ownership" check), then `docker compose up -d --build <service>`. The data lives in the
   `crm-data` volume and survives a rebuild.
8. **Rollback:** delete `routes.d/sbi-relationship-crm.conf`, `nginx -t`, reload; `docker compose down` in this
   project only (never `-v` unless a backup is confirmed - it holds the database volume).
9. **Android:** build the release app against the same link:
   `./gradlew assembleRelease -PrcrmApiBaseUrl=https://indev.eko.in/sbi-relationship-crm/api/v1/`.

Transcription runs in the `transcription` container (CPU Speaches image; `TRANSCRIPTION_PROVIDER=openai` is set
in compose). Allow minutes for a long call: `TRANSCRIPTION_TIMEOUT_SECONDS` defaults to 900 in compose.

## SQLite under load

The app opens SQLite in **WAL** mode with a 30 s busy timeout (`app/db.py`), so readers and the single writer do not
block each other. Consequences: next to the database file there are `-wal` and `-shm` files while it is running;
the nightly backup uses SQLite's backup API (safe); but a plain copy of `relationship_crm.db` from a running
server can miss the newest writes, so take backups through the app's backup, `sqlite3 <db> ".backup <out>"`, or
stop the backend cleanly first. The database must be on a local disk (a Docker volume is fine), not a network
share. If writes keep waiting (sustained "database is locked"), that is the sign to move to PostgreSQL (below).

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

## Stakeholder graph

Edges between officials (`reports_to` / `works_with` / `introduced_by`). Manual
edges (`POST /api/v1/connections`, admin/RM) land `confirmed`. When an
interaction is logged, officials named in it are proposed as `suggested`
`works_with` edges; a human confirms or dismisses them per official
(`PATCH /api/v1/connections/{id}`). `POST /api/v1/officials/{id}/connections/rescan`
re-runs the suggestion pass over that official's interactions — use it to
backfill data loaded before the feature existed. Only `confirmed` edges appear
in the Relationship Brief.

## Tuning (all in `.env`, restart to apply)

| Variable | Default | Effect |
|---|---|---|
| `SESSION_TTL_HOURS` | 8 | login session lifetime |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | (unset) → offline stub | OpenAI-compatible endpoint for interaction extraction and the Relationship Brief narrative |
| `LLM_TIMEOUT_SECONDS` | 30 | per-call timeout; raise for slow local models |
| `MOMENT_LOOKAHEAD_DAYS` | 7 | how far ahead birthdays / anniversaries are surfaced |
| `MOMENT_INACTIVITY_DAYS` | 35 | silence before an inactivity moment |
| `MOMENT_FATIGUE_DAYS` | 21 | recent-contact window that suppresses a moment |
| `MOMENT_PROMOTION_RECENT_DAYS` | 30 | how recent a promotion date must be |
| `OVERDUE_ESCALATION_DAYS` | 3 | (reserved for a future escalation tier) |
| `ENABLE_BACKUPS` | true | kill switch for the nightly automated backup |
| `BACKUP_DIR` | `backups` | backup folder, relative to the database file's directory |
| `BACKUP_RETENTION_COUNT` | 7 | how many nightly snapshots to keep |
| `RM_RECORDING_RETENTION_DAYS` | 60 | RM-CSP call audio is deleted this many days after it was stored (audio only; transcripts are not purged) - see `docs/data-retention.md` |
| `MEDIA_DELETE_MAX_ATTEMPTS` | 8 | failed file deletions are retried with backoff, then marked abandoned and audited |
| `MEDIA_ORPHAN_GRACE_HOURS` / `MEDIA_ORPHAN_MAX_PER_RUN` | 24 / 50 | orphan-file sweep: minimum file age, and the per-run safety cap that aborts the sweep |
| `COMMITMENT_PROPOSAL_EXPIRY_DAYS` | 30 | an unreviewed AI-proposed commitment expires after this many days |
| `COMMITMENT_CLOSED_RETENTION_DAYS` | 730 | a done/cancelled commitment is deleted this many days after it was closed (open ones never expire) |
| `INTELLIGENCE_FEEDBACK_RETENTION_DAYS` | 730 | a useful / relevant verdict on a suggestion is deleted this many days after it was last changed |
| `MEMORY_LOOKBACK_DAYS` | 365 | only call briefs this recent feed a CSP's relationship memory |
| `ENABLE_RAG` | true | kill switch for RAG retrieval in `/ask` and the Brief narrative |
| `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` | (unset) → falls back to `LLM_BASE_URL`, then the offline stub | OpenAI-compatible `/embeddings` endpoint |
| `EMBEDDING_DIM` | 256 | dimension of the offline stub's hashed vectors only |
| `RAG_TOP_K` | 5 | max retrieved chunks per `/ask` answer |
| `RAG_MAX_CHARS_BUDGET` | 4000 | context-size cap for retrieved excerpts |
| `RAG_MIN_SIMILARITY` | 0.15 | cosine-similarity floor below which a chunk is dropped |
| `ENABLE_SEMANTIC_MEMORY` | true | kill switch for fact extraction from interaction notes |
| `ENABLE_STRATEGIC_INSIGHTS` | true | kill switch for the nightly strategic-insight recompute |
| `STRATEGIC_INSIGHT_MIN_SAMPLE` | 5 | minimum sample size before a strategic insight is created |

## RAG, memory, and learning

- **RAG** — `services/embeddings.py` mirrors `services/llm.py`'s shape exactly
  (real endpoint if configured, deterministic offline stub otherwise, never
  raises). Chunks come from `Interaction.raw_notes`, sent
  `EngagementMoment.draft_text`, and `Opportunity.detail` — there is no
  separate "document" model. `POST /api/v1/knowledge/reindex` (admin) rebuilds
  the whole index, e.g. after changing the embedding model.
- **Semantic memory** — `GET/POST /api/v1/officials/{id}/facts`,
  `.../facts/{fact_id}/verify`, `.../facts/{fact_id}/reject`. A
  human-confirmed fact is never silently overwritten by a lower-confidence
  auto-extraction; conflicts are recorded in the audit log
  (`semantic_memory.fact.conflict_ignored`).
- **Strategic memory** — `GET /api/v1/officials/{id}/insights`,
  `POST .../insights/recompute` (admin). Response-rate insights use a
  documented proxy signal (a subsequent inbound interaction stands in for a
  confirmed reply) — always labeled `proxy_signal: true` in the evidence,
  never presented as ground truth.
- **Outcome tracking** — `GET /api/v1/agent/recommendations/{id}/outcome`,
  `GET /api/v1/agent/outcomes`, `GET /api/v1/agent/evaluation`,
  `POST /api/v1/agent/outcomes/reconcile` (admin/RM, on-demand — the nightly
  job runs the same reconciliation automatically).
- **Strategy registry & experiments** — `/api/v1/strategies/*` (admin-only).
  A strategy version can only be promoted from an experiment that has
  `status=completed` and at least `minimum_sample_size` relationships in the
  treatment arm (default 20) — promotion is always one explicit admin
  action, never automatic. Today only one strategy is wired to actual agent
  behavior — `task_followup_timing`, which overrides the follow-up
  `due_in_days` the stub recommender uses (`services/strategy.py`); an
  unassigned relationship's behavior is unaffected.

## Tests

```bash
pytest -q                                  # 240+ tests, in-memory SQLite
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

`GET /api/v1/health` → `{status, time, database, last_backup_at}`. `status` is
`degraded` if the database is unreachable; `last_backup_at` is `null` if
backups are disabled or none have run yet.
