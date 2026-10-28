"""Database engine, session factory, and the FastAPI session dependency."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

settings = get_settings()

# timeout: how long (s) a writer waits for the single SQLite write lock before "database is locked".
_connect_args = {"check_same_thread": False, "timeout": 30} if settings.is_sqlite else {}

engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False
)

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets readers and the one writer run side by side (the default journal blocks one with the
        # other), which matters with many users uploading and the background transcription writing.
        # synchronous=NORMAL is the standard pairing: still safe across a crash with WAL.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def get_db() -> Iterator[Session]:
    """Yield a session; roll back on error, always close. Handlers commit explicitly."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
