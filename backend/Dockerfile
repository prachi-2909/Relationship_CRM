# Production image for the FastAPI backend. Runs migrations on start, then
# serves the app. SQLite by default (see README's "Moving to Postgres later")
# - mount a volume at /app/data and point DATABASE_URL there for persistence.
FROM python:3.11-slim

WORKDIR /app

# System deps for bcrypt/psycopg wheels are unnecessary on slim + manylinux
# wheels, but curl is handy for the healthcheck and debugging.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8010/api/v1/health || exit 1

# Apply any pending migrations, then start the server. Never falls back to
# --reload here - that's a dev-only convenience (see .claude/launch.json).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8010"]
